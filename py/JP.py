import socket
import time
import threading
import ipaddress
import random
from queue import Queue
from datetime import datetime
import requests

# === 测速配置参数 ===
TEST_TIMEOUT = 2        # 测试超时时间(秒) - 建议2秒以内，太慢的节点没有价值
MAX_THREADS = 50        # 并发线程数
TOP_NODES = 50          # 保存前N个最快节点
TXT_OUTPUT_FILE = "JP_Nodes.txt"  # 输出文件

# === Cloudflare 数据中心(Colo) 对应国家/地区映射表 ===
COLO_MAP = {
    'NRT': '日本 (东京)',
    'KIX': '日本 (大阪)',
    'OKA': '日本 (冲绳)',
    'LAX': '美国 (洛杉矶)',
    'SJC': '美国 (圣何塞)',
    'SFO': '美国 (旧金山)',
    'SEA': '美国 (西雅图)',
    'HKG': '中国香港',
    'TPE': '中国台湾',
    'SIN': '新加坡',
    'ICN': '韩国 (首尔)',
    'LHR': '英国 (伦敦)',
    'FRA': '德国 (法兰克福)'
}

class CloudflareNodeTester:
    def __init__(self):
        self.nodes = set()
        self.results =[]
        self.lock = threading.Lock()
        
        # 禁用requests的安全警告(由于我们直接请求IP)
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    def fetch_known_nodes(self):
        """生成待测试的IP节点"""
        
        # 你可以添加更多的 CF 优选 IP 段
        ip_ranges =[
            '108.162.198.0/22',
            # '104.28.0.0/24', # 其他常用段示例
        ]
        
        print(f"开始解析 IP 网段...")
        for ip_range in ip_ranges:
            try:
                # 使用 ipaddress 库准确解析网段下的所有IP
                network = ipaddress.IPv4Network(ip_range, strict=False)
                # 排除网络号和广播地址
                hosts = list(network.hosts())
                
                # 如果单个网段 IP 太多 (如 /22 有 1022 个可用IP)，为防耗时过长，可以采用随机抽样
                # 如果想测试全部，请删除下面三行，直接写: for ip in hosts:
                sample_size = min(len(hosts), 100)  # 这里每个网段随机抽取100个测试
                sampled_ips = random.sample(hosts, sample_size)
                
                for ip in sampled_ips:
                    self.nodes.add(str(ip))
            except Exception as e:
                print(f"网段解析失败 {ip_range}: {e}")
                
        print(f"共生成了 {len(self.nodes)} 个待测 IP。\n")

    def test_node_speed(self, ip):
        """
        利用 Cloudflare 的 cdn-cgi/trace 接口：
        1. 验证它确实是CF节点
        2. 拿到真实的延迟
        3. 获取实际的落地机房 (colo)
        """
        try:
            start_time = time.time()
            url = f"http://{ip}/cdn-cgi/trace"
            
            # 发起请求
            response = requests.get(url, timeout=TEST_TIMEOUT)
            
            # 判断是否为 Cloudflare 节点
            if response.status_code == 200 and 'colo=' in response.text:
                response_time = int((time.time() - start_time) * 1000)
                
                # 解析真实的机房位置
                colo = "Unknown"
                for line in response.text.split('\n'):
                    if line.startswith('colo='):
                        colo = line.split('=')[1].strip()
                        break
                
                country_name = COLO_MAP.get(colo, f"未知地区 ({colo})")
                
                return {
                    'ip': ip,
                    'reachable': True,
                    'response_time_ms': response_time,
                    'colo': colo,
                    'country': country_name
                }
        except Exception:
            pass # 无法连接或超时，静默失败
            
        return {'ip': ip, 'reachable': False}
    
    def worker(self, queue):
        """多线程工作者"""
        while not queue.empty():
            ip = queue.get()
            try:
                result = self.test_node_speed(ip)
                if result['reachable']:
                    with self.lock:
                        self.results.append(result)
            finally:
                queue.task_done()
    
    def test_all_nodes(self):
        """使用多线程并发测试所有节点"""
        print(f"开始进行测速和定位，当前并发线程数: {MAX_THREADS} ...")
        queue = Queue()
        for ip in self.nodes:
            queue.put(ip)
            
        threads =[]
        for _ in range(min(MAX_THREADS, len(self.nodes))):
            t = threading.Thread(target=self.worker, args=(queue,))
            t.start()
            threads.append(t)
            
        # 阻塞等待所有测试完成
        for t in threads:
            t.join()
            
        print(f"测速完成！存活节点数: {len(self.results)}/{len(self.nodes)}\n")

    def sort_and_display_results(self):
        """排序并打印结果"""
        # 按延迟升序排序
        sorted_nodes = sorted(self.results, key=lambda x: x['response_time_ms'])
        
        print("===== 测速结果 (前50名) =====")
        print(f"{'IP地址':<18} | {'延迟':<6} | {'真实落地位置'}")
        print("-" * 50)
        
        for i, node in enumerate(sorted_nodes[:TOP_NODES], 1):
            # 高亮标识是否真的是日本
            is_jp = "★ " if node['colo'] in ['NRT', 'KIX', 'OKA'] else "  "
            print(f"{is_jp}{node['ip']:<16} | {node['response_time_ms']}ms  | {node['country']}")
            
        return sorted_nodes
    
    def save_results(self, results):
        """将结果按通用代理格式保存到本地"""
        top_results = results[:TOP_NODES]
        if not top_results:
            print("没有找到存活节点，无法保存。")
            return
            
        with open(TXT_OUTPUT_FILE, 'w', encoding='utf-8') as f:
            for node in top_results:
                # 输出格式例如: 108.162.198.12:443#【日本 (东京)】NRT_120ms
                line = f"{node['ip']}:443#【{node['country']}】{node['colo']}_{node['response_time_ms']}ms\n"
                f.write(line)
                
        print(f"\n结果已成功保存至 {TXT_OUTPUT_FILE}")

    def run(self):
        """执行主流程"""
        start_time = time.time()
        self.fetch_known_nodes()
        self.test_all_nodes()
        sorted_nodes = self.sort_and_display_results()
        self.save_results(sorted_nodes)
        print(f"总耗时: {int(time.time() - start_time)} 秒")

if __name__ == "__main__":
    try:
        tester = CloudflareNodeTester()
        tester.run()
    except KeyboardInterrupt:
        print("\n[!] 用户中断了测速程序")
    except Exception as e:
        print(f"\n[!] 运行出错: {e}")
