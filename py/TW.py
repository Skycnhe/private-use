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
MAX_THREADS = 100    # GitHub Actions 建议 50-100
TOP_NODES = 50       
TXT_OUTPUT_FILE = "Global_IP.txt" 

# Cloudflare 官方 IPv4 全量网段
CF_IPV4_RANGES = [
    '173.245.48.0/20', '103.21.244.0/22', '103.22.200.0/22',
    '103.31.4.0/22', '141.101.64.0/18', '108.162.192.0/18',
    '190.93.240.0/20', '188.114.96.0/20', '197.234.240.0/22',
    '198.41.128.0/17', '162.158.0.0/15', '104.16.0.0/12',
    '172.64.0.0/13', '131.0.72.0/22'
]

# 国家映射表
COUNTRY_LABELS = {
    'HK': '中国香港', 'TW': '中国台湾', 'JP': '日本', 
    'KR': '韩国', 'SG': '新加坡', 'US': '美国', 
    'DE': '德国', 'CN': '中国'
}

def get_real_location(ip):
    """识别IP归属地"""
    try:
        # ip-api.com 免费限速 45次/分钟，我们只查 TOP 节点，不会超限
        url = f"http://ip-api.com/json/{ip}?fields=status,countryCode"
        resp = requests.get(url, timeout=5).json()
        if resp.get('status') == 'success':
            code = resp.get('countryCode')
            label = COUNTRY_LABELS.get(code, code)
            return code, label
        return "Unknown", "未知区域"
    except:
        return "Error", "查询失败"

class CloudflareTester:
    def __init__(self):
        self.nodes = set()
        self.results = []
        self.lock = threading.Lock()
    
    def fetch_nodes(self):
        """解析全球网段并采样"""
        print("[*] 正在解析全量网段样本...")
        for cidr in CF_IPV4_RANGES:
            try:
                net = ipaddress.ip_network(cidr)
                # 智能采样步长
                if net.num_addresses <= 1024:
                    step = 8
                elif net.num_addresses <= 65536:
                    step = 256
                else:
                    step = 1024
                
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

        print(f"[*] 开始测速，线程数: {MAX_THREADS}...")
        threads = []
        for _ in range(MAX_THREADS):
            t = threading.Thread(target=self.worker, args=(q,))
            t.daemon = True
            t.start()
            threads.append(t)
        
        q.join()
        
        # 排序
        sorted_nodes = sorted(self.results, key=lambda x: x['ms'])
        
        # 识别归属地并保存
        print(f"[*] 识别前 {TOP_NODES} 个节点的国家信息...")
        final_data = []
        for i in range(min(len(sorted_nodes), TOP_NODES)):
            node = sorted_nodes[i]
            code, label = get_real_location(node['ip'])
            node['code'] = code.lower()
            node['label'] = label
            final_data.append(node)
            print(f"Rank {i+1}: {node['ip']} | {node['ms']}ms | {label}")
            time.sleep(0.3) # 防止API请求过快

        self.save(final_data)

    def save(self, data):
        with open(TXT_OUTPUT_FILE, 'w', encoding='utf-8') as f:
            for n in data:
                # 按照 IP#code 【国家】 地区代码 格式输出
                line = f"{n['ip']}#{n['code']} 【{n['label']}】 {n['code'].upper()}\n"
                f.write(line)
        print(f"[*] 成功保存至 {TXT_OUTPUT_FILE}")

if __name__ == "__main__":
    try:
        tester = CloudflareTester()
        tester.run()
    except Exception as e:
        print(f"[!] 程序异常退出: {e}")
