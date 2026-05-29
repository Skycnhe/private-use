import socket
import re
import time
import threading
import requests  # 移动到顶部防止报错
from queue import Queue
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Cloudflare节点测试配置参数
TEST_TIMEOUT = 3  # 测试超时时间(秒)
TEST_PORT = 443   # 测试端口
MAX_THREADS = 10  # 稍微增加线程提高效率
TOP_NODES = 50    # 显示和保存前N个最快节点
TXT_OUTPUT_FILE = "JP.txt"    # TXT结果保存文件
IP_COUNTRIES_FILE = "IP_Countries.txt" # 定义缺失的变量

# 国家代码到中文国家名称的映射
COUNTRY_CODES = {
    'US': '美国', 'CN': '中国', 'JP': '日本', 'SG': '新加坡', 'KR': '韩国',
    'GB': '英国', 'FR': '法国', 'DE': '德国', 'AU': '澳大利亚', 'CA': '加拿大',
    'HK': '中国香港', 'TW': '中国台湾', 'IN': '印度', 'RU': '俄罗斯', 'Unknown': '未知'
}

def get_ip_country(ip):
    """获取IP地址对应的国家信息(增加异常处理)"""
    try:
        session = requests.Session()
        # 针对 Anycast IP，API 往往返回美国。为了防止请求过快被封，这里简单处理
        url = f"http://ip-api.com/json/{ip}?fields=countryCode"
        response = session.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            code = data.get('countryCode', 'Unknown')
            return COUNTRY_CODES.get(code, code)
        return '未知'
    except:
        return '查询失败'

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
        # 针对中国电信优选日本/亚洲节点
        ip_ranges = [
            '104.16.0.0/12',
            '172.64.0.0/13',
            '162.159.0.0/16',
            '108.162.192.0/18'
        ]
        for ip_range in ip_ranges:
            base_ip = ip_range.split('/')[0]
            octets = base_ip.split('.')
            # 每个段抽样生成，避免基数过大
            for i in range(1, 21): 
                ip = f"{octets[0]}.{octets[1]}.{octets[2]}.{i}"
                self.nodes.add(ip)
    
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
        return {'ip': ip, 'reachable': False, 'response_time_ms': None}
    
    def worker(self, queue):
        while not queue.empty():
            ip = queue.get()
            result = self.test_node_speed(ip)
            with self.lock:
                self.results.append(result)
                if len(self.results) % 10 == 0:
                    print(f"进度: {len(self.results)}/{len(self.nodes)}")
            queue.task_done()
    
    def test_all_nodes(self):
        queue = Queue()
        for ip in self.nodes: queue.put(ip)
        threads = []
        for _ in range(min(MAX_THREADS, len(self.nodes))):
            thread = threading.Thread(target=self.worker, args=(queue,))
            thread.start()
            threads.append(thread)
        for thread in threads: thread.join()
    
    def sort_and_display_results(self):
        reachable_nodes = [n for n in self.results if n['reachable']]
        sorted_nodes = sorted(reachable_nodes, key=lambda x: x['response_time_ms'])
        
        print("\n[最快节点列表]")
        for i, node in enumerate(sorted_nodes[:TOP_NODES], 1):
            # 注意：频繁查API会被封，这里只查前5个，其余标记
            country = "待查" if i > 5 else get_ip_country(node['ip'])
            print(f"{node['ip']} - {node['response_time_ms']}ms - {country}")
        return sorted_nodes

    def save_results(self, results):
        try:
            top_results = results[:TOP_NODES]
            with open(TXT_OUTPUT_FILE, 'w', encoding='utf-8') as f:
                for node in top_results:
                    # 写入格式优化
                    f.write(f"{node['ip']}:443#JP_Cloudflare_{node['response_time_ms']}ms\n")
            print(f"\n结果已保存至 {TXT_OUTPUT_FILE}")
        except Exception as e:
            print(f"保存失败: {e}")

def run_cloudflare_tester(self):
    print("正在获取节点...")
    self.fetch_known_nodes()
    print(f"开始测试 {len(self.nodes)} 个节点...")
    self.test_all_nodes()
    sorted_nodes = self.sort_and_display_results()
    self.save_results(sorted_nodes)

CloudflareNodeTester.run = run_cloudflare_tester

if __name__ == "__main__":
    try:
        tester = CloudflareNodeTester()
        tester.run()
    except Exception as e:
        print(f"程序运行崩溃: {e}")
