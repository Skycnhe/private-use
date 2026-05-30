import socket
import re
import time
import threading
import ipaddress
import requests
from queue import Queue

# ================= 配置参数 =================
TEST_TIMEOUT = 1.0   # 延迟测试超时(秒)
TEST_PORT = 443      
MAX_THREADS = 100    # 并发线程
TARGET_COUNT = 50    # 目标收集多少个台湾IP
TARGET_COUNTRY = "TW" # 筛选的国家代码
TXT_OUTPUT_FILE = "TW.txt" 

# Cloudflare 官方 IPv4 网段
CF_IPV4_RANGES = [
    '173.245.48.0/20', '103.21.244.0/22', '103.22.200.0/22',
    '103.31.4.0/22', '141.101.64.0/18', '108.162.192.0/18',
    '190.93.240.0/20', '188.114.96.0/20', '197.234.240.0/22',
    '198.41.128.0/17', '162.158.0.0/15', '104.16.0.0/12',
    '172.64.0.0/13', '131.0.72.0/22'
]

def get_real_location(ip):
    """识别IP归属地"""
    try:
        # ip-api.com 免费版限制 45次/分钟
        # 如果需要大规模查询，建议使用本地库（如 MaxMind）
        url = f"http://ip-api.com/json/{ip}?fields=status,countryCode"
        resp = requests.get(url, timeout=5).json()
        if resp.get('status') == 'success':
            return resp.get('countryCode')
        return "Unknown"
    except:
        return "Error"

class CloudflareTester:
    def __init__(self):
        self.nodes = set()
        self.results = []
        self.lock = threading.Lock()
    
    def fetch_nodes(self):
        """解析网段样本"""
        print("[*] 正在解析全量网段样本...")
        for cidr in CF_IPV4_RANGES:
            try:
                net = ipaddress.ip_network(cidr)
                # 采样步长：网段越大，步长越大，避免样本过多
                if net.num_addresses <= 1024:
                    step = 8
                elif net.num_addresses <= 65536:
                    step = 128
                else:
                    step = 512
                
                for i in range(1, net.num_addresses, step):
                    self.nodes.add(str(net[i]))
            except:
                continue
        print(f"[*] 样本生成完毕: {len(self.nodes)} 个候选节点")

    def test_latency(self, ip):
        """测试连接延迟"""
        try:
            start_time = time.time()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(TEST_TIMEOUT)
                if s.connect_ex((ip, TEST_PORT)) == 0:
                    return int((time.time() - start_time) * 1000)
        except:
            pass
        return None

    def worker(self, queue):
        while not queue.empty():
            ip = queue.get()
            ms = self.test_latency(ip)
            if ms:
                with self.lock:
                    self.results.append({'ip': ip, 'ms': ms})
            queue.task_done()

    def run(self):
        self.fetch_nodes()
        q = Queue()
        for ip in self.nodes:
            q.put(ip)

        print(f"[*] 开始测速（第一轮：筛选低延迟节点），线程数: {MAX_THREADS}...")
        threads = []
        for _ in range(MAX_THREADS):
            t = threading.Thread(target=self.worker, args=(q,))
            t.daemon = True
            t.start()
            threads.append(t)
        
        q.join()
        
        # 按照延迟从低到高排序
        sorted_nodes = sorted(self.results, key=lambda x: x['ms'])
        
        print(f"[*] 开始识别归属地，目标：{TARGET_COUNTRY}，计划收集：{TARGET_COUNT}个...")
        final_data = []
        count = 0
        
        # 遍历测速结果，查找符合国家代码的IP
        for node in sorted_nodes:
            if count >= TARGET_COUNT:
                break
                
            code = get_real_location(node['ip'])
            
            if code == TARGET_COUNTRY:
                node['code'] = code.lower()
                node['label'] = "中国台湾"
                final_data.append(node)
                count += 1
                print(f"找到第 {count} 个台湾节点: {node['ip']} | {node['ms']}ms")
            
            # 关键：ip-api 免费版有限制，每分钟最多45次
            # 为了防止被封IP，这里增加一个小延迟，或者如果你有付费Key可以移除
            time.sleep(1.35) 

        if final_data:
            self.save(final_data)
        else:
            print("[!] 未找到符合条件的台湾节点。")

    def save(self, data):
        with open(TXT_OUTPUT_FILE, 'w', encoding='utf-8') as f:
            for n in data:
                # 格式：IP#code 【国家】 地区代码
                line = f"{n['ip']}#{n['code']} 【{n['label']}】 {n['code'].upper()}\n"
                f.write(line)
        print(f"[*] 成功保存 {len(data)} 个节点至 {TXT_OUTPUT_FILE}")

if __name__ == "__main__":
    try:
        tester = CloudflareTester()
        tester.run()
    except Exception as e:
        print(f"[!] 程序异常退出: {e}")
