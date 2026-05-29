import socket
import re
import time
import threading
import ipaddress
from queue import Queue
from datetime import datetime
import requests

# ================= 配置参数 =================
TEST_TIMEOUT = 1.5  
TEST_PORT = 443   
MAX_THREADS = 100   # 建议增加到 100，提高效率
TOP_NODES = 20    
TXT_OUTPUT_FILE = "TW.txt"

# Cloudflare 官方 IPv4 网段
CF_IPV4_RANGES = [
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

class CloudflareNodeTester:
    def __init__(self):
        self.nodes = set()
        self.results = []
        self.lock = threading.Lock()
    
    def fetch_known_nodes(self):
        """生成待测IP样本"""
        print(f"[*] 正在从 {len(CF_IPV4_RANGES)} 个官方网段中生成样本...")
        for cidr in CF_IPV4_RANGES:
            try:
                net = ipaddress.ip_network(cidr)
                # 采样逻辑
                if net.num_addresses <= 1024:
                    step = 8
                elif net.num_addresses <= 65536:
                    step = 128
                else:
                    step = 512
                
                # 遍历网段进行采样
                for i in range(1, net.num_addresses, step):
                    self.nodes.add(str(net[i]))
                
                # 针对核心段增加额外样本
                if "104.16" in cidr or "172.64" in cidr:
                    for j in range(1, 10):
                        self.nodes.add(str(net[j]))
            except Exception as e:
                print(f"解析网段 {cidr} 出错: {e}")

        print(f"[*] 生成了 {len(self.nodes)} 个待测节点")

    def test_node_speed(self, ip):
        """TCP 握手测速"""
        try:
            start_time = time.time()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(TEST_TIMEOUT)
                result = s.connect_ex((ip, TEST_PORT))
                if result == 0:
                    latency = (time.time() - start_time) * 1000
                    return {'ip': ip, 'reachable': True, 'latency': int(latency)}
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
                        print(f"[+] 已发现 {len(self.results)} 个可用节点...")
            queue.task_done()

    def run(self):
        start_time = time.time()
        self.fetch_known_nodes()
        
        task_queue = Queue()
        for ip in self.nodes:
            task_queue.put(ip)
        
        print(f"[*] 开始测速，线程数: {MAX_THREADS}...")
        threads = []
        for _ in range(MAX_THREADS):
            # 修复：thread.setDaemon(True) 在新版本中已弃用，改为 daemon 属性
            t = threading.Thread(target=self.worker, args=(task_queue,))
            t.daemon = True 
            t.start()
            threads.append(t)
        
        task_queue.join()
        
        # 排序并保存
        sorted_nodes = sorted(self.results, key=lambda x: x['latency'])
        self.save_results(sorted_nodes)
        print(f"[*] 总耗时: {int(time.time() - start_time)}秒")

    def save_results(self, results):
        count = min(len(results), TOP_NODES)
        try:
            with open(TXT_OUTPUT_FILE, 'w', encoding='utf-8') as f:
                for i in range(count):
                    node = results[i]
                    # 严格执行你要求的格式
                    f.write(f"{node['ip']}#tw 【中国台湾】 TW\n")
            print(f"[*] 结果已保存至 {TXT_OUTPUT_FILE}，共 {count} 个")
        except Exception as e:
            print(f"保存文件出错: {e}")

if __name__ == "__main__":
    # 确保安装了 requests: pip install requests
    try:
        tester = CloudflareNodeTester()
        tester.run()
    except KeyboardInterrupt:
        print("\n[!] 用户停止运行")
    except Exception as e:
        print(f"[!] 程序运行错误: {e}")            if result['reachable']:
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
