import socket
import time
import ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed

# ================= 配置参数 =================
TEST_TIMEOUT = 1.0     # 连接超时时间（秒）
TEST_PORT = 443        # 测试端口
MAX_THREADS = 150      # 并发线程数（根据电脑配置可调高）
TOP_NODES = 20         # 最终保留的优选数量
TXT_OUTPUT_FILE = "JP.txt" # 修改为 JP.txt

# Cloudflare 官方 IPv4 网段 (这些网段在 Anycast 下可能指向全球任何数据中心)
# 注：对于中国大陆用户，以下网段中 104.16.x.x / 172.64.x.x / 108.162.x.x 
# 经常能扫出延迟较低的东京 (NRT) 或 大阪 (KIX) 节点。
CF_IPV4_RANGES = [
    '173.245.48.0/20', '103.21.244.0/22', '103.22.200.0/22',
    '103.31.4.0/22', '141.101.64.0/18', '108.162.192.0/18',
    '190.93.240.0/20', '188.114.96.0/20', '197.234.240.0/22',
    '198.41.128.0/17', '162.158.0.0/15', '104.16.0.0/12',
    '172.64.0.0/13', '131.0.72.0/22'
]

class CloudflareScanner:
    def __init__(self):
        self.ips = []
        self.results = []

    def generate_ips(self):
        """解析网段并抽样生成待测 IP"""
        print("[*] 正在解析官方网段并生成样本...")
        for cidr in CF_IPV4_RANGES:
            network = ipaddress.ip_network(cidr)
            # 步进采样：大网段步进更大，防止总数过多
            if network.num_addresses > 10000:
                step = 256  # 大型网段每 256 个 IP 取一个
            elif network.num_addresses > 1024:
                step = 64   # 中型网段每 64 个 IP 取一个
            else:
                step = 16   # 小型网段每 16 个 IP 取一个
            
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
        print(f"[*] 开始日本方向测速 (并发线程: {MAX_THREADS})...")
        
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

        # 按延迟排序（延迟越低越靠前）
        self.results.sort(key=lambda x: x['latency'])
        
        duration = int(time.time() - start_time)
        print(f"[*] 测速完成，耗时 {duration} 秒，有效节点 {len(self.results)} 个")
        self.save_top_nodes()

    def save_top_nodes(self):
        """保存为 JP 格式"""
        count = min(len(self.results), TOP_NODES)
        if count == 0:
            print("[!] 未发现可用节点，请检查网络环境。")
            return

        try:
            with open(TXT_OUTPUT_FILE, "w", encoding="utf-8") as f:
                for i in range(count):
                    node = self.results[i]
                    # 修改为 JP 格式标识
                    f.write(f"{node['ip']}#jp 【日本】 JP\n")
            
            print(f"[*] 结果已保存至 {TXT_OUTPUT_FILE}")
            print("\n延迟最低的前 5 个日本方向节点:")
            for i in range(min(5, count)):
                print(f"  {self.results[i]['ip']} - {self.results[i]['latency']}ms")
        except Exception as e:
            print(f"[!] 保存失败: {e}")

if __name__ == "__main__":
    scanner = CloudflareScanner()
    try:
        scanner.run()
    except KeyboardInterrupt:
        print("\n[!] 用户停止")
