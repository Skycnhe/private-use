import socket
import re
import time
import threading
import ipaddress  # 引入处理IP段的库
from queue import Queue
from datetime import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Cloudflare节点测试配置参数
TEST_TIMEOUT = 1.5  # 降低超时时间，提高扫描速度
TEST_PORT = 443   
MAX_THREADS = 50    # 增加线程数，否则测不完正常的IP段
TOP_NODES = 20    
TXT_OUTPUT_FILE = "TW.txt"

COUNTRY_CODES = {
    'US': '美国', 'CN': '中国', 'JP': '日本', 'SG': '新加坡', 'KR': '韩国',
    'GB': '英国', 'FR': '法国', 'DE': '德国', 'AU': '澳大利亚', 'CA': '加拿大',
    'HK': '中国香港', 'TW': '中国台湾', 'IN': '印度', 'RU': '俄罗斯', 'Unknown': '未知'
}

def get_ip_country(ip):
    """获取IP地址对应的国家信息"""
    try:
        url = f"http://ip-api.com/json/{ip}?fields=countryCode"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            code = data.get('countryCode', 'Unknown')
            return COUNTRY_CODES.get(code, code)
        return '未知'
    except:
        return '未知'

def clean_ip(ip_str):
    ip_str = ip_str.strip().split('#')[0].split(':')[0]
    pattern = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'
    if re.match(pattern, ip_str):
        return ip_str
    return None

class CloudflareNodeTester:
    def __init__(self):
        self.nodes = set()
        self.results = []
        self.lock = threading.Lock()
    
    def fetch_known_nodes(self):
        """生成Cloudflare官方标准的IPv4节点列表"""
        # 修改点：更新为官方最新的 IPv4 网段列表
        cf_ipv4_ranges = [
            '173.245.48.0/20',
            '103.21.244.0/22',
            '103.22.200.0/22',
            '103.31.4.0/22',
            '141.101.64.0/18',
            '108.162.192.0/18',
            '190.93.240.0/20',
            '188.114.96.0/20',
            '197.234.240.0/22',
            '198.41.128.0/17',
            '162.158.0.0/15',
            '104.16.0.0/12',
            '172.64.0.0/13',
            '131.0.72.0/22'
        ]
        
        print(f"正在从 {len(cf_ipv4_ranges)} 个官方网段中生成测试样本...")
        
        for cidr in cf_ipv4_ranges:
            net = ipaddress.ip_network(cidr)
            # 逻辑：从每个定义的网段中均匀抽取一部分IP进行探测
            # 如果网段很小，多取点；网段很大（如/12），按大步长取样
            if net.num_addresses <= 1024:
                step = 10 
            elif net.num_addresses <= 65536:
                step = 128 
            else:
                step = 512 # 针对 104.16/12 等超大网段，增加步长以防样本过载
            
            count = 0
            for i in range(1, net.num_addresses, step):
                self.nodes.add(str(net[i]))
                count += 1
                
            # 针对经常出现优选节点的特定段，额外增加一些样本
            if "104.16" in cidr or "172.64" in cidr:
                 for j in range(1, 15): self.nodes.add(str(net[j]))

        print(f"生成了 {len(self.nodes)} 个待测节点。")

    def test_node_speed(self, ip):
        try:
            start_time = time.time()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(TEST_TIMEOUT)
                result = s.connect_ex((ip, TEST_PORT))
                if result == 0:
                    response_time = (time.time() - start_time) * 1000
                    return {'ip': ip, 'reachable': True, 'response_time_ms': int(response_time)}
        except:
            pass
        return {'ip': ip, 'reachable': False}

    def worker(self, queue):
        while not queue.empty():
            ip = queue.get()
            result = self.test_node_speed(ip)
            if result['reachable']:
                with self.lock:
                    self.results.append(result)
                    if len(self.results) % 50 == 0:
                        print(f"找到 {len(self.results)} 个可用节点...")
            queue.task_done()

    def test_all_nodes(self):
        queue = Queue()
        for ip in self.nodes:
            queue.put(ip)
        
        threads = []
        for _ in range(min(MAX_THREADS, len(self.nodes))):
            thread = threading.Thread(target=self.worker, args=(queue,))
            thread.setDaemon(True)
            thread.start()
            threads.append(thread)
        
        queue.join()

    def sort_and_display_results(self):
        reachable_nodes = [n for n in self.results if n['reachable']]
        sorted_nodes = sorted(reachable_nodes, key=lambda x: x['response_time_ms'])
        
        print(f"\n测速完成，最快的 {TOP_NODES} 个节点：")
        for node in sorted_nodes[:TOP_NODES]:
            print(f"{node['ip']} - 延迟: {node['response_time_ms']}ms")
        return sorted_nodes

    def save_results(self, results):
        try:
            with open(TXT_OUTPUT_FILE, 'w', encoding='utf-8') as f:
                for node in results[:TOP_NODES]:
                    # 统一按照格式输出
                    f.write(f"{node['ip']}#tw 【中国台湾】 TW\n")
            print(f"结果已保存至 {TXT_OUTPUT_FILE}")
        except Exception as e:
            print(f"保存失败: {e}")

    def run(self):
        start_time = time.time()
        self.fetch_known_nodes()
        print(f"开始进行多线程测速（线程数: {MAX_THREADS}）...")
        self.test_all_nodes()
        sorted_nodes = self.sort_and_display_results()
        self.save_results(sorted_nodes)
        print(f"总耗时: {int(time.time() - start_time)}秒")

if __name__ == "__main__":
    try:
        tester = CloudflareNodeTester()
        tester.run()
    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"程序出错: {e}")            ip = queue.get()
            result = self.test_node_speed(ip)
            if result['reachable']:
                with self.lock:
                    self.results.append(result)
                    if len(self.results) % 50 == 0:
                        print(f"找到 {len(self.results)} 个可用节点...")
            queue.task_done()

    def test_all_nodes(self):
        queue = Queue()
        for ip in self.nodes:
            queue.put(ip)
        
        threads = []
        for _ in range(min(MAX_THREADS, len(self.nodes))):
            thread = threading.Thread(target=self.worker, args=(queue,))
            thread.setDaemon(True)
            thread.start()
            threads.append(thread)
        
        queue.join()

    def sort_and_display_results(self):
        reachable_nodes = [n for n in self.results if n['reachable']]
        sorted_nodes = sorted(reachable_nodes, key=lambda x: x['response_time_ms'])
        
        print(f"\n测速完成，最快的 {TOP_NODES} 个节点：")
        for node in sorted_nodes[:TOP_NODES]:
            print(f"{node['ip']} - 延迟: {node['response_time_ms']}ms")
        return sorted_nodes

    def save_results(self, results):
        try:
            with open(TXT_OUTPUT_FILE, 'w', encoding='utf-8') as f:
                for node in results[:TOP_NODES]:
                    # 统一按照你要求的格式输出
                    f.write(f"{node['ip']}#tw 【中国台湾】 TW\n")
            print(f"结果已保存至 {TXT_OUTPUT_FILE}")
        except Exception as e:
            print(f"保存失败: {e}")

    def run(self):
        start_time = time.time()
        self.fetch_known_nodes()
        print(f"开始进行多线程测速（线程数: {MAX_THREADS}）...")
        self.test_all_nodes()
        sorted_nodes = self.sort_and_display_results()
        self.save_results(sorted_nodes)
        print(f"总耗时: {int(time.time() - start_time)}秒")

if __name__ == "__main__":
    try:
        tester = CloudflareNodeTester()
        tester.run()
    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"程序出错: {e}")
