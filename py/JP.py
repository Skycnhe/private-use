import socket
import re
import time
import threading
from queue import Queue
from datetime import datetime

# ================= 配置参数 =================
TEST_TIMEOUT = 3      # 测试超时时间(秒)
TEST_PORT = 443       # 测试端口
MAX_THREADS = 10      # 最大线程数 (日本节点较多，适当增加)
TOP_NODES = 20        # 显示前N个最快节点
TXT_OUTPUT_FILE = "JP.txt"    # TXT结果保存文件
# ===========================================

# Cloudflare 节点测试类
class CloudflareNodeTester:
    def __init__(self):
        self.nodes = set()  # 存储节点IP
        self.results = []   # 存储测试结果
        self.lock = threading.Lock()
    
    def fetch_known_nodes(self):
        """配置针对日本区域优化的 IP 段"""
        # 这些是 Cloudflare 在亚洲常跳日本的 IP 网段示例
        ip_ranges = [
            "104.16.160.0/24",
            "108.162.193.0/24",
            "162.159.211.0/24",
            "172.64.33.0/24",
            "104.17.159.0/24"
        ]
        
        for ip_range in ip_ranges:
            base_ip, cidr = ip_range.split('/')
            octets = base_ip.split('.')
            # 每个网段生成部分 IP 进行扫描（1-50）
            for i in range(1, 51):
                ip = f"{octets[0]}.{octets[1]}.{octets[2]}.{i}"
                self.nodes.add(ip)
    
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
                        'response_time_ms': int(response_time)
                    }
        except:
            pass
        return {'ip': ip, 'reachable': False, 'response_time_ms': None}

    def worker(self, queue):
        """线程工作函数"""
        while not queue.empty():
            ip = queue.get()
            try:
                res = self.test_node_speed(ip)
                if res['reachable']:
                    with self.lock:
                        self.results.append(res)
                        if len(self.results) % 10 == 0:
                            print(f"已找到 {len(self.results)} 个可用日本节点...")
            finally:
                queue.task_done()

    def test_all_nodes(self):
        """启动多线程测试"""
        print(f"正在测试 {len(self.nodes)} 个潜在日本 IP...")
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
        """排序并打印结果"""
        # 按响应时间升序排序
        sorted_nodes = sorted(self.results, key=lambda x: x['response_time_ms'])
        
        print(f"\n===== 测试完成 (前 {TOP_NODES} 名) =====")
        for i, node in enumerate(sorted_nodes[:TOP_NODES], 1):
            print(f"{node['ip']}#jp 【日本】 JP ({node['response_time_ms']}ms)")
        
        return sorted_nodes

    def save_results(self, results):
        """保存前 30 名结果到 JP.txt"""
        try:
            # 取前 30 名
            top_results = results[:30]
            with open(TXT_OUTPUT_FILE, 'w', encoding='utf-8') as f:
                for node in top_results:
                    # 严格按照要求的格式写入
                    line = f"{node['ip']}#jp 【日本】 JP\n"
                    f.write(line)
            print(f"\n结果已保存至: {TXT_OUTPUT_FILE}")
        except Exception as e:
            print(f"保存失败: {e}")

    def run(self):
        start_time = time.time()
        self.fetch_known_nodes()
        self.test_all_nodes()
        sorted_nodes = self.sort_and_display_results()
        self.save_results(sorted_nodes)
        print(f"总耗时: {int(time.time() - start_time)} 秒")

# ================= 主程序 =================
if __name__ == "__main__":
    try:
        tester = CloudflareNodeTester()
        tester.run()
    except KeyboardInterrupt:
        print("\n用户中断测试")
    except Exception as e:
        print(f"程序运行出错: {e}")
