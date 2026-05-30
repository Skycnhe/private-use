import socket
import time
import ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed

# ================= 配置参数 =================
TEST_TIMEOUT = 1.0     # 连接超时时间（秒）
TEST_PORT = 443        # 测试端口
MAX_THREADS = 100      # 并发线程数
TOP_NODES = 20         # 最终保留的优选数量
TXT_OUTPUT_FILE = "JP.txt"

# Cloudflare 官方 IPv4 网段
CF_IPV4_RANGES = [
    '173.245.48.0/20', '103.21.244.0/22', '103.22.200.0/22',
    '103.31.4.0/22', '141.101.64.0/18', '108.162.192.0/18',
    '190.93.240.0/20', '188.114.96.0/20', '197.234.240.0/22',
    '198.41.128.0/17', '162.158.0.0/15', '104.16.0.0/12',
    '172.64.0.0/13', '131.0.72.0/22'
]

class CloudflareScannerJP:
    def __init__(self):
        self.ips = []
        self.results = []

    def generate_ips(self):
        """解析网段并抽样生成待测 IP"""
        print("[*] 正在解析官方网段并生成日本优选样本...")
        for cidr in CF_IPV4_RANGES:
            try:
                network = ipaddress.ip_network(cidr)
                # 抽样逻辑：大网段步长 128，小网段步长 16
                step = 128 if network.num_addresses > 1024 else 16
                for i in range(1, network.num_addresses, step):
                    self.ips.append(str(network[i]))
            except:
                continue
        print(f"[*] 样本生成完毕，共有 {len(self.ips)} 个测试目标")

    def test_latency(self, ip):
        """测试 TCP 握手延迟"""
        try:
            start = time.perf_counter()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(TEST_TIMEOUT)
                result = s.connect_ex((ip, TEST_PORT))
                if result == 0:
                    latency = (time.perf_counter() - start) * 1000
                    return {"ip": ip, "latency": int(latency)}
        except:
            pass
        return None

    def run(self):
        self.generate_ips()
        print(f"[*] 开始测速 (并发线程: {MAX_THREADS})...")
        
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
            future_to_ip = {executor.submit(self.test_latency, ip): ip for ip in self.ips}
            
            completed = 0
            for future in as_completed(future_to_ip):
                res = future.result()
                if res:
                    self.results.append(res)
                
                completed += 1
                if completed % 500 == 0:
                    print(f"    进度: {completed}/{len(self.ips)}...")

        # 排序
        self.results.sort(key=lambda x: x['latency'])
        
        duration = int(time.time() - start_time)
        print(f"[*] 测速完成，耗时 {duration} 秒，有效节点 {len(self.results)} 个")
        self.save_top_nodes()

    def save_top_nodes(self):
        """保存为指定格式"""
        count = min(len(self.results), TOP_NODES)
        if count == 0:
            print("[!] 未发现可用节点")
            return

        try:
            with open(TXT_OUTPUT_FILE, "w", encoding="utf-8") as f:
                for i in range(count):
                    node = self.results[i]
                    # 格式：IP#jp 【日本】 JP
                    f.write(f"{node['ip']}#jp 【日本】 JP\n")
            
            print(f"[*] 结果已保存至 {TXT_OUTPUT_FILE}")
            for i in range(min(5, count)):
                print(f"  优选: {self.results[i]['ip']} ({self.results[i]['latency']}ms)")
        except Exception as e:
            print(f"[!] 保存失败: {e}")

if __name__ == "__main__":
    scanner = CloudflareScannerJP()
    try:
        scanner.run()
    except KeyboardInterrupt:
        print("\n[!] 用户停止")
    except Exception as e:
        print(f"\n[!] 程序运行出错: {e}")            country = "待查" if i > 5 else get_ip_country(node['ip'])
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
