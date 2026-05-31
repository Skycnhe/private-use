import socket
import re
import time
import threading
import ipaddress
from queue import Queue
from datetime import datetime

# ================= Cloudflare节点测试配置参数 =================
TEST_TIMEOUT = 1.5  # 测试超时时间(秒)
TEST_PORT = 443     # 测试端口
MAX_THREADS = 100   # 最大线程数
TOP_NODES = 20      # 显示和保存前N个最快节点
TXT_OUTPUT_FILE = "JP.txt"    # 结果保存文件

# ================= 辅助函数 =================
def get_ip_country(ip):
    """固定返回日本标签"""
    return '日本'

def clean_ip(ip_str):
    """清理IP字符串"""
    ip_str = ip_str.strip().rstrip(':')
    pattern = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'
    if re.match(pattern, ip_str):
        parts = ip_str.split('.')
        if all(0 <= int(part) <= 255 for part in parts):
            return ip_str
    return None

# ================= Cloudflare节点测试类 =================
class CloudflareNodeTester:
    def __init__(self):
        self.nodes = set()  # 存储节点IP
        self.results = []   # 存储测试结果
        self.lock = threading.Lock()
    
    def fetch_known_nodes(self):
        """解析CF网段并采样生成IP"""
        ip_ranges = [
            '173.245.48.0/20', '103.21.244.0/22', '103.22.200.0/22',
            '103.31.4.0/22', '141.101.64.0/18', '108.162.192.0/18',
            '190.93.240.0/20', '188.114.96.0/20', '197.234.240.0/22',
            '198.41.128.0/17', '162.158.0.0/15', '104.16.0.0/13',
            '172.64.0.0/13'
        ]
        
        print(f"[*] 正在解析网段采样生成 IP...")
        for cidr in ip_ranges:
            try:
                network = ipaddress.ip_network(cidr)
                # 根据网段大小自动调整采样步长
                if network.num_addresses <= 1024:
                    step = 8
                elif network.num_addresses <= 65536:
                    step = 128
                else:
                    step = 512
                
                hosts = list(network.hosts())
                for i in range(0, len(hosts), step):
                    self.nodes.add(str(hosts[i]))
            except:
                continue
        print(f"[*] 采样完成，共生成 {len(self.nodes)} 个待测 IP")
    
    def test_node_speed(self, ip):
        """测试单个节点的连接速度"""
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
        """线程工作函数"""
        while not queue.empty():
            try:
                ip = queue.get_nowait()
            except:
                break
            result = self.test_node_speed(ip)
            if result['reachable']:
                with self.lock:
                    self.results.append(result)
            queue.task_done()
    
    def test_all_nodes(self):
        """测试所有节点的速度"""
        print(f"[*] 启动线程池进行测速 (最大线程: {MAX_THREADS})...")
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
    
    def sort_and_display_results(self):
        """排序并显示测试结果"""
        sorted_nodes = sorted(self.results, key=lambda x: x['response_time_ms'])
        print(f"[*] 测速完成，发现响应节点: {len(sorted_nodes)}")
        for i, node in enumerate(sorted_nodes[:min(10, len(sorted_nodes))], 1):
            print(f"  {i}. {node['ip']} - {node['response_time_ms']}ms")
        return sorted_nodes
    
    def save_results(self, results):
        """保存结果到文件"""
        try:
            top_results = results[:TOP_NODES]
            with open(TXT_OUTPUT_FILE, 'w', encoding='utf-8') as f:
                for node in top_results:
                    f.write(f"{node['ip']}#jp 【日本】 JP\n")
            print(f"[*] 结果已成功保存到 {TXT_OUTPUT_FILE}")
        except Exception as e:
            print(f"[!] 保存失败: {e}")

# ================= 动态绑定 run 方法 =================
def run_cloudflare_tester(self):
    """运行流程"""
    start_time = time.time()
    self.fetch_known_nodes()
    self.test_all_nodes()
    sorted_nodes = self.sort_and_display_results()
    self.save_results(sorted_nodes)
    print(f"[*] 脚本总耗时: {int(time.time() - start_time)} 秒")

CloudflareNodeTester.run = run_cloudflare_tester

# ================= 主入口 =================
if __name__ == "__main__":
    try:
        tester = CloudflareNodeTester()
        tester.run()
    except KeyboardInterrupt:
        print("\n[!] 用户中断程序")
    except Exception as e:
        print(f"\n[!] 运行出错: {e}")
