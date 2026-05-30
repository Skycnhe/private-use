import socket
import time
import threading
import ipaddress
import requests
import os
from queue import Queue

# ================= 配置参数 =================
TEST_TIMEOUT = 1.0       # 延迟测试超时(秒)
HTTP_TIMEOUT = 2.0       # 获取地区信息的超时(秒)
TEST_PORT = 443          # 测试端口
MAX_THREADS = 100        # 并发线程数
TARGET_PER_REGION = 20   # 每个地区收集多少个IP后停止（或者作为保存上限）

# 目标地区配置：IATA代码映射到中文和文件名前缀
REGION_CONFIG = {
    'JP': {'name': '日本', 'codes': ['NRT', 'KIX', 'FUK', 'NGO'], 'file': 'JP.txt'},
    'HK': {'name': '中国香港', 'codes': ['HKG'], 'file': 'HK.txt'},
    'KR': {'name': '韩国', 'codes': ['ICN'], 'file': 'KR.txt'},
    'TW': {'name': '中国台湾', 'codes': ['TPE', 'KHH'], 'file': 'TW.txt'},
    'SG': {'name': '新加坡', 'codes': ['SIN'], 'file': 'SG.txt'},
    'DE': {'name': '德国', 'codes': ['FRA', 'MUC', 'HAM', 'DUS'], 'file': 'DE.txt'},
    'US': {'name': '美国', 'codes': ['SJC', 'LAX', 'SFO', 'SEA', 'ORD', 'JFK', 'IAD'], 'file': 'US.txt'}
}

# Cloudflare 官方 IPv4 网段
CF_IPV4_RANGES = [
    '173.245.48.0/20', '103.21.244.0/22', '103.22.200.0/22',
    '103.31.4.0/22', '141.101.64.0/18', '108.162.192.0/18',
    '190.93.240.0/20', '188.114.96.0/20', '197.234.240.0/22',
    '198.41.128.0/17', '162.158.0.0/15', '104.16.0.0/12',
    '172.64.0.0/13', '131.0.72.0/22'
]

class CloudflareMultiScanner:
    def __init__(self):
        self.nodes = []
        self.results = {reg: [] for reg in REGION_CONFIG} # 按地区分类存储结果
        self.lock = threading.Lock()
    
    def fetch_nodes(self):
        """生成待测样本（智能采样）"""
        print("[*] 正在解析 Cloudflare 全量网段样本...")
        seen_ips = set()
        for cidr in CF_IPV4_RANGES:
            net = ipaddress.ip_network(cidr)
            # 这里的 step 可以根据需求调整，数字越大扫描越快但越粗略
            step = 256 if net.num_addresses > 1024 else 32
            for i in range(1, net.num_addresses, step):
                ip = str(net[i])
                if ip not in seen_ips:
                    self.nodes.append(ip)
                    seen_ips.add(ip)
        print(f"[*] 样本生成完毕: {len(self.nodes)} 个候选节点")

    def get_ip_info(self, ip):
        """测试延迟并识别真实位置"""
        try:
            # 1. 测延迟 (TCP)
            start_time = time.time()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(TEST_TIMEOUT)
                if s.connect_ex((ip, TEST_PORT)) != 0:
                    return None
                latency = int((time.time() - start_time) * 1000)

            # 2. 测位置 (HTTP Trace)
            # 这里的 Host 头部可以使用任一接入 CF 的域名
            trace_url = f"http://{ip}/cdn-cgi/trace"
            resp = requests.get(trace_url, headers={"Host": "cloudflare.com"}, timeout=HTTP_TIMEOUT)
            if resp.status_code == 200:
                # 寻找 colo=XXX 这一行
                for line in resp.text.split('\n'):
                    if line.startswith('colo='):
                        colo_code = line.split('=')[1]
                        return {'ip': ip, 'ms': latency, 'colo': colo_code}
        except:
            pass
        return None

    def worker(self, queue):
        while not queue.empty():
            ip = queue.get()
            info = self.get_ip_info(ip)
            if info:
                # 匹配归属地
                found_match = False
                for reg_code, config in REGION_CONFIG.items():
                    if info['colo'] in config['codes']:
                        with self.lock:
                            self.results[reg_code].append(info)
                            found_match = True
                        break
            queue.task_done()

    def run(self):
        self.fetch_nodes()
        q = Queue()
        for ip in self.nodes:
            q.put(ip)

        print(f"[*] 正在全速识别地区并测试延迟 (线程: {MAX_THREADS})...")
        print("[*] 提示: 正在使用 Cloudflare 内部接口，无需等待，速度极快。")
        
        threads = []
        for _ in range(MAX_THREADS):
            t = threading.Thread(target=self.worker, args=(q,))
            t.daemon = True
            t.start()
            threads.append(t)
        
        q.join()
        self.save_all()

    def save_all(self):
        print("\n" + "="*30)
        print("扫描任务完成，正在分类保存结果...")
        
        for reg_code, nodes in self.results.items():
            if not nodes:
                continue
            
            config = REGION_CONFIG[reg_code]
            # 按延迟排序
            sorted_nodes = sorted(nodes, key=lambda x: x['ms'])
            
            with open(config['file'], 'w', encoding='utf-8') as f:
                # 仅保存前 TARGET_PER_REGION 个最快的
                save_count = 0
                for n in sorted_nodes[:TARGET_PER_REGION]:
                    # 按照你要求的格式：IP#code 【国家】 地区代码
                    line = f"{n['ip']}#{reg_code.lower()} 【{config['name']}】 {reg_code}\n"
                    f.write(line)
                    save_count += 1
                
            print(f"  [+] {config['name']} ({reg_code}): 已保存 {save_count} 个节点至 {config['file']}")
        print("="*30)

if __name__ == "__main__":
    try:
        scanner = CloudflareMultiScanner()
        scanner.run()
    except KeyboardInterrupt:
        print("\n[!] 用户停止任务")
    except Exception as e:
        print(f"[!] 程序异常: {e}")
