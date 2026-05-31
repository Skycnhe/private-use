import socket
import re
import time
import threading
import ipaddress
from queue import Queue
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ================= 配置参数 =================
TEST_TIMEOUT = 1.5  # 测试超时时间(秒)
TEST_PORT = 443     # 测试端口
MAX_THREADS = 50    # 最大线程数 (日本优化段较多，建议稍微调大)
TOP_NODES = 30      # 显示和保存前N个最快节点
TXT_OUTPUT_FILE = "JP.txt"  # 结果保存文件

# 日本方向（中国优化线路）典型 IP 段
TARGET_RANGES = [
    # --- 电信 CN2 GIA / 联通 AS9929 优化段 ---
    '45.160.232.0/24', '154.31.112.0/24', '103.151.216.0/24', '156.251.139.0/24',
    
    # --- 联通神线：日本软银 (Softbank / BBTEC) ---
    '103.156.184.0/24', '118.238.0.0/16', '161.202.0.0/16', '103.201.128.0/22',
    
    # --- IIJ 线路 (AS2497) ---
    '202.221.0.0/16', '103.2.248.0/22', '103.20.196.0/22',
    
    # --- 移动 CMI / 直连优化 ---
    '103.135.248.0/24', '103.114.160.0/23', '45.14.64.0/24',
    
    # --- 热门云服务商日本节点 (GCP/Oracle/AWS 采样) ---
    '34.84.0.0/16', '158.101.64.0/18', '130.162.0.0/16'
]

COUNTRY_CODES = {
    'JP': '日本', 'CN': '中国', 'US': '美国', 'HK': '中国香港', 'KR': '韩国'
}

def get_ip_country(ip):
    """获取IP地址对应的国家信息(简化版，优先返回日本)"""
    # 针对这些特定段，我们已知是日本，为了速度直接返回
    return "日本"

def clean_ip(ip_str):
    ip_str = ip_str.strip().rstrip(':')
    pattern = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'
    if re.match(pattern, ip_str):
        parts = ip_str.split('.')
        if all(0 <= int(part) <= 255 for part in parts):
            return ip_str
    return None

class CloudflareNodeTester:
    def __init__(self):
        self.nodes = set()
        self.results = []
        self.lock = threading.Lock()
    
    def fetch_known_nodes(self):
        """解析目标网段并采样生成待测IP"""
        print("[*] 正在解析日本优化线路网段...")
        for cidr in TARGET_RANGES:
            try:
                network = ipaddress.ip_network(cidr)
                # 采样逻辑：避免扫描整个 B 段
                if network.num_addresses <= 256:
                    step = 8
                elif network.num_addresses <= 4096:
                    step = 64
                else:
                    step = 256
                
                hosts = list(network.hosts())
                for i in range(0, len(hosts), step):
                    self.nodes.add(str(hosts[i]))
            except Exception as e:
                print(f"解析网段 {cidr} 出错: {e}")
        print(f"[*] 采样完成，共生成 {len(self.nodes)} 个待测节点")
    
    def test_node_speed(self, ip):
        try:
            start_time = time.time()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(TEST_TIMEOUT)
                result = s.connect_ex((ip, TEST_PORT))
                if result == 0:
                    response_time = (time.time() - start_time) * 1000
                    return {
                        'ip': ip,
                        'reachable': True,
                        'response_time_ms': int(response_time)
                    }
        except:
            pass
        return {'ip': ip, 'reachable': False, 'response_time_ms': None}
    
    def worker(self, queue):
        while not queue.empty():
            try:
                ip = queue.get_nowait()
            except:
                break
            result = self.test_node_speed(ip)
            with self.lock:
                if result['reachable']:
                    self.results.append(result)
                if (len(self.results) + 1) % 50 == 0:
                    # 这里的计数仅作为活跃参考
                    pass
            queue.task_done()
    
    def test_all_nodes(self):
        print(f"[*] 开始测速，线程数: {MAX_THREADS}...")
        queue = Queue()
        for ip in self.nodes:
            queue.put(ip)
        
        threads = []
        for _ in range(min(MAX_THREADS, len(self.nodes))):
            thread = threading.Thread(target=self.worker, args=(queue,))
            thread.daemon = True
            thread.start()
            threads.append(thread)
        
        for thread in threads:
            thread.join()
        print(f"[*] 测速完成，发现响应节点: {len(self.results)} 个")
    
    def sort_and_display_results(self):
        sorted_nodes = sorted(self.results, key=lambda x: x['response_time_ms'])
        print("\n===== 延迟最低节点预览 =====")
        for i, node in enumerate(sorted_nodes[:10], 1):
            print(f"[{i}] {node['ip']} - {node['response_time_ms']}ms (日本)")
        return sorted_nodes
    
    def save_results(self, results):
        try:
            top_results = results[:TOP_NODES]
            with open(TXT_OUTPUT_FILE, 'w', encoding='utf-8') as f:
                for node in top_results:
                    # 保持您要求的输出格式
                    line = f"{node['ip']}#jp 【日本】 JP\n"
                    f.write(line)
            print(f"\n[*] 结果已保存至 {TXT_OUTPUT_FILE}")
        except Exception as e:
            print(f"保存结果失败: {e}")

    def run(self):
        start_time = time.time()
        self.fetch_known_nodes()
        self.test_all_nodes()
        sorted_nodes = self.sort_and_display_results()
        self.save_results(sorted_nodes)
        print(f"[*] 总耗时: {int(time.time() - start_time)}s")

if __name__ == "__main__":
    tester = CloudflareNodeTester()
    try:
        tester.run()
    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"程序出错: {e}")
