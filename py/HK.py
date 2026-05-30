import socket
import time
import ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed

# ================= 配置参数 =================
TEST_TIMEOUT = 1.0     # 连接超时时间（秒）
TEST_PORT = 443        # 测试端口
MAX_THREADS = 100      # 并发线程数
TOP_NODES = 20         # 最终保留的优选数量
TXT_OUTPUT_FILE = "TW.txt"  # 修改为台湾文件名

# Cloudflare 官方 IPv4 网段
CF_IPV4_RANGES = [
    '173.245.48.0/20', '103.21.244.0/22', '103.22.200.0/22',
    '103.31.4.0/22', '141.101.64.0/18', '108.162.192.0/18',
    '190.93.240.0/20', '188.114.96.0/20', '197.234.240.0/22',
    '198.41.128.0/17', '162.158.0.0/15', '104.16.0.0/12',
    '172.64.0.0/13', '131.0.72.0/22'
]

class CloudflareScannerTW:
    def __init__(self):
        self.ips = []
        self.results = []

    def generate_ips(self):
        """解析网段并抽样生成待测 IP"""
        print("[*] 正在解析官方网段并生成台湾优选样本...")
        for cidr in CF_IPV4_RANGES:
            network = ipaddress.ip_network(cidr)
            # 抽样逻辑：大网段每隔 128 个 IP 取一个，小网段每隔 16 个取一个
            if network.num_addresses > 1024:
                step = 128
            else:
                step = 16
            
            for i in range(1, network.num_addresses, step):
                self.ips.append(str(network[i]))
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

        # 按延迟从低到高排序
        self.results.sort(key=lambda x: x['latency'])
        
        duration = int(time.time() - start_time)
        print(f"[*] 测速完成，耗时 {duration} 秒，获得有效节点 {len(self.results)} 个")
        self.save_top_nodes()

    def save_top_nodes(self):
        """保存为台湾格式"""
        count = min(len(self.results), TOP_NODES)
        if count == 0:
            print("[!] 未发现可用节点。")
            return

        try:
            with open(TXT_OUTPUT_FILE, "w", encoding="utf-8") as f:
                for i in range(count):
                    node = self.results[i]
                    # 格式：IP#tw 【中国台湾】 TW
                    f.write(f"{node['ip']}#tw 【中国台湾】 TW\n")
            
            print(f"[*] 优选完成，结果已保存至 {TXT_OUTPUT_FILE}")
            print("\n延迟最低的前 5 个台湾备选节点:")
            for i in range(min(5, count)):
                print(f"  {self.results[i]['ip']} - {self.results[i]['latency']}ms")
        except Exception as e:
            print(f"[!] 保存失败: {e}")

if __name__ == "__main__":
    scanner = CloudflareScannerTW()
    try:
        scanner.run()
    except KeyboardInterrupt:
        print("\n[!] 用户停止")
