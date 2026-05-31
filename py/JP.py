import socket
import re
import time
import threading
import ipaddress
from queue import Queue
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Cloudflare节点测试配置参数
TEST_TIMEOUT = 1.5  # 测试超时时间(秒)
TEST_PORT = 443     # 测试端口
MAX_THREADS = 100   # 最大线程数
TOP_NODES = 20      # 显示和保存前N个最快节点
TXT_OUTPUT_FILE = "JP.txt"    # 结果保存文件

# 国家代码到中文国家名称的映射
COUNTRY_CODES = {
    'US': '美国',
    'CN': '中国',
    'JP': '日本',
    'SG': '新加坡',
    'KR': '韩国',
    'HK': '中国香港',
    'TW': '中国台湾',
    'Unknown': '未知'
}

# IP地理位置查询函数
def get_ip_country(ip):
    """获取IP地址对应的国家信息"""
    # 为了扫描效率，由于是CF日本段测试，此处直接返回日本
    # 这样可以避免因频繁请求API导致的程序卡顿
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

# Cloudflare节点测试类
class CloudflareNodeTester:
    def __init__(self):
        self.nodes = set()  # 存储节点IP
        self.results = []   # 存储测试结果
        self.lock = threading.Lock()
    
    def fetch_known_nodes(self):
        """从Cloudflare官方IP段生成测试目标"""
        # Cloudflare 常用 IPv4 网段
        ip_ranges = [
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
            '104.16.0.0/13',
            '172.64.0.0/13'
        ]
        
        print(f"[*] 正在从 {len(ip_ranges)} 个网段中采样生成 IP...")
        for cidr in ip_ranges:
            try:
                network = ipaddress.ip_network(cidr)
                # 采样逻辑：根据网段大小调整步进，确保覆盖面且不会测试太多
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
                if result == 0:  # 连接成功
                    response_time = (time.time() - start_time) * 1000
                    return {
                        'ip': ip,
                        'reachable': True,
                        'response_time_ms': int(response_time),
                        'timestamp': datetime.now().isoformat()
                    }
        except:
            pass
        return {
            'ip': ip,
            'reachable': False,
            'response_time_ms': None,
            'timestamp': datetime.now().isoformat()
        }
    
    def worker(self, queue):
        """线程工作函数"""
        while not queue.empty():
            try:
                ip = queue.get_nowait()
            except:
                break
            result = self.test_node_speed(ip)
            with self.lock:
                if result['reachable']:
                    self.results.append(result)
                # 进度提示
                count = len(self.results)
                if count > 0 and count % 100 == 0:
                    pass 
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
            thread.start()
            threads.append(thread)
        
        for thread in threads:
            thread.join()
    
    def sort_and_display_results(self):
        """排序并显示测试结果"""
        # 过滤出可连接的节点
        reachable_nodes = [
            node for node in self.results 
            if node['reachable'] and node['response_time_ms'] is not None
        ]
        
        # 按响应时间升序排序
        sorted_nodes = sorted(
            reachable_nodes, 
            key=lambda x: x['response_time_ms']
        )
        
        print(f"\n[*] 测速完成，响应节点总数: {len(sorted_nodes)}")
        # 显示前N个最快节点
        for i, node in enumerate(sorted_nodes[:TOP_NODES], 1):
            print(f"{node['ip']}#jp 【日本】 JP - {node['response_time_ms']}ms")
        
        return sorted_nodes
    
    def save_results(self, results):
        """保存结果到TXT文件"""
        try:
            top_results = results[:TOP_NODES]
            with open(TXT_OUTPUT_FILE, 'w', encoding='utf-8') as f:
                for node in top_results:
                    # 格式：IP#jp 【日本】 JP
                    line = f"{node['ip']}#jp 【日本】 JP\n"
                    f.write(line)
            print(f"\n[*] 优选结果已保存到 {TXT_OUTPUT_FILE}")
        except Exception as e:
            print(f"保存结果失败: {e}")

# CloudflareNodeTester类的run方法
def run_cloudflare_tester(self):
    """运行整个测试流程"""
    start_time = time.time()
    
    # 1. 生成待测IP
    self.fetch_known_nodes()
    
    # 2. 测试所有节点
    self.test_all_nodes()
    
    # 3. 排序并显示结果
    sorted_nodes = self.sort_and_display_results()
    
    # 4. 保存结果
    self.save_results(sorted_nodes)
    
    total_time = int(time.time() - start_time)
    print(f"[*] 脚本运行总耗时: {total_time} 秒")

# 添加run方法到CloudflareNodeTester类
CloudflareNodeTester.run = run_cloudflare_tester

# 主函数
if __name__ == "__main__":
    try:
        tester = CloudflareNodeTester()
        tester.run()
    except KeyboardInterrupt:
        print("\n用户中断了程序")
    except Exception as e:
        print(f"程序出错: {e}")            
            print(f"[*] 优选完成！前 5 名低延迟节点：")
            for i in range(min(5, count)):
                print(f"    {self.results[i]['ip']} - {self.results[i]['response_time_ms']}ms")
            print(f"[*] 结果已存入: {TXT_OUTPUT_FILE}")
        except Exception as e:
            print(f"[!] 文件保存失败: {e}")

if __name__ == "__main__":
    tester = CloudflareNodeTester()
    try:
        tester.run()
    except KeyboardInterrupt:
        print("\n[!] 任务被用户中断")    
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
