import socket
import time
import threading
import ipaddress
import requests
import os
import sys
from queue import Queue

# ================= 配置参数 =================
TEST_TIMEOUT = 1.0       # TCP延迟测试超时(秒)
HTTP_TIMEOUT = 1.5       # 获取地区信息的超时(秒)
TEST_PORT = 443          # 测试端口
MAX_THREADS = 100        # 并发线程数
TARGET_PER_REGION = 30   # 每个地区收集多少个IP后停止（保存上限）

# 目标地区配置：完善了更多机房代码
REGION_CONFIG = {
    'JP': {'name': '日本', 'codes': ['NRT', 'KIX', 'FUK', 'NGO', 'HND'], 'file': 'JP.txt'},
    'HK': {'name': '中国香港', 'codes': ['HKG'], 'file': 'HK.txt'},
    'KR': {'name': '韩国', 'codes': ['ICN', 'PUS'], 'file': 'KR.txt'},
    'TW': {'name': '中国台湾', 'codes': ['TPE', 'KHH'], 'file': 'TW.txt'},
    'SG': {'name': '新加坡', 'codes': ['SIN'], 'file': 'SG.txt'},
    'DE': {'name': '德国', 'codes': ['FRA', 'MUC', 'HAM', 'DUS', 'TXL', 'BER'], 'file': 'DE.txt'},
    'US': {'name': '美国', 'codes': ['SJC', 'LAX', 'SFO', 'SEA', 'ORD', 'JFK', 'IAD', 'DFW', 'EWR', 'ATL'], 'file': 'US.txt'}
}

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
        self.results = {reg: [] for reg in REGION_CONFIG}
        self.counter = {reg: 0 for reg in REGION_CONFIG} # 用于显示进度
        self.lock = threading.Lock()
        self.start_time = 0
        self.is_running = True

    def fetch_nodes(self):
        """生成待测样本：更科学的散列抽样"""
        print("[*] 正在解析 Cloudflare 全量网段并生成样本...")
        for cidr in CF_IPV4_RANGES:
            net = ipaddress.ip_network(cidr)
            # 根据网段大小动态调整步长
            if net.num_addresses > 65536: step = 512
            elif net.num_addresses > 4096: step = 128
            else: step = 64
            
            # 每个网段内分散取样
            for i in range(1, net.num_addresses, step):
                self.nodes.append(str(net[i]))
        print(f"[*] 样本生成完毕: {len(self.nodes)} 个候选节点")

    def get_ip_info(self, ip):
        """核心探测逻辑：TCP延迟 + HTTP Trace机房识别"""
        try:
            # 1. 延迟探测
            s_time = time.time()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(TEST_TIMEOUT)
                if s.connect_ex((ip, TEST_PORT)) != 0:
                    return None
                latency = int((time.time() - s_time) * 1000)

            # 2. 识别机房 (使用 HTTP 1.1 减少开销)
            trace_url = f"http://{ip}/cdn-cgi/trace"
            resp = requests.get(trace_url, headers={"Host": "da.gd"}, timeout=HTTP_TIMEOUT)
            if resp.status_code == 200:
                for line in resp.text.split('\n'):
                    if line.startswith('colo='):
                        return {'ip': ip, 'ms': latency, 'colo': line.split('=')[1]}
        except:
            pass
        return None

    def worker(self, q):
        while not q.empty() and self.is_running:
            ip = q.get()
            info = self.get_ip_info(ip)
            if info:
                # 匹配预设地区
                for reg_code, config in REGION_CONFIG.items():
                    if info['colo'] in config['codes']:
                        with self.lock:
                            self.results[reg_code].append(info)
                            self.counter[reg_code] += 1
                            # 实时刷新进度条
                            self.print_progress()
                        break
            q.task_done()

    def print_progress(self):
        """在同一行刷新显示各地区获取数量"""
        stats = " | ".join([f"{k}:{v}" for k, v in self.counter.items()])
        sys.stdout.write(f"\r[*] 发现节点 -> {stats} ")
        sys.stdout.flush()

    def save_results(self):
        """任务结束，排序并保存"""
        print("\n\n[*] 正在按延迟排序并保存结果...")
        for reg_code, nodes in self.results.items():
            if not nodes: continue
            
            config = REGION_CONFIG[reg_code]
            # 按延迟从低到高排序
            sorted_nodes = sorted(nodes, key=lambda x: x['ms'])
            
            with open(config['file'], 'w', encoding='utf-8') as f:
                for n in sorted_nodes[:TARGET_PER_REGION]:
                    # 格式：IP#code 【国家】 地区代码
                    line = f"{n['ip']}#{reg_code.lower()} 【{config['name']}】 {reg_code}\n"
                    f.write(line)
            print(f"  [+] {config['name']} 优选完成，已保存至 {config['file']}")

    def run(self):
        self.start_time = time.time()
        self.fetch_nodes()
        
        q = Queue()
        for ip in self.nodes:
            q.put(ip)

        print(f"[*] 启动线程池: {MAX_THREADS} 线程，目标每地区 {TARGET_PER_REGION} 个优质节点")
        
        threads = []
        for _ in range(MAX_THREADS):
            t = threading.Thread(target=self.worker, args=(q,))
            t.daemon = True
            t.start()
            threads.append(t)

        try:
            # 持续检查队列，直到全部处理完成
            while not q.empty():
                time.sleep(1)
            q.join()
        except KeyboardInterrupt:
            print("\n[!] 用户强制停止，正在保存已发现的数据...")
            self.is_running = False

        self.save_results()
        total_time = int(time.time() - self.start_time)
        print(f"\n[*] 全部任务耗时: {total_time} 秒")

if __name__ == "__main__":
    scanner = CloudflareMultiScanner()
    scanner.run()        print("\n" + "="*30)
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
