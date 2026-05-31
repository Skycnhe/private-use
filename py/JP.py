import socket
import time
import ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed

# ================= 配置参数 =================
TEST_TIMEOUT = 1.0     # 连接超时时间（秒）
TEST_PORT = 443        # 测试端口
MAX_THREADS = 150      # 并发线程数（略微调高以应对更多IP）
TOP_NODES = 20         # 最终保留的优选数量
TXT_OUTPUT_FILE = "JP.txt"

# 所有目标 IP 段（已将单 IP 转换为 /24 段）
TARGET_RANGES = [
    # 原始请求段
    '151.101.108.0/22', 
    '146.75.112.0/22',
    # 第一批单 IP 转换
    '35.72.217.0/24',
    '35.75.36.0/24',
    '54.250.99.0/24',
    '54.150.255.0/24',
    '54.150.38.0/24',
    '54.199.210.0/24',
    # 新增单 IP 转换 (AWS Japan 等)
    '18.178.194.0/24',
    '15.168.134.0/24',
    '13.208.106.0/24',
    '18.176.54.0/24',
    '52.194.252.0/24',
    '15.152.150.0/24',
    '3.112.13.0/24'
]

class IPScannerJP:
    def __init__(self):
        self.ips = []
        self.results = []

    def generate_ips(self):
        """解析所有网段并生成待测 IP 列表"""
        print("[*] 正在解析目标 IP 段并生成样本...")
        for cidr in TARGET_RANGES:
            try:
                network = ipaddress.ip_network(cidr)
                # 采样策略优化：
                # /24 段 (256 IP) 每隔 2 个测一个 (step=2)
                # /22 段 (1024 IP) 每隔 8 个测一个 (step=8)
                # 如果你想扫描每个 IP，把下面的 step 统一改为 1
                if network.num_addresses <= 256:
                    step = 2
                else:
                    step = 8
                
                for i in range(0, network.num_addresses, step):
                    self.ips.append(str(network[i]))
            except Exception as e:
                print(f"[!] 网段解析错误 {cidr}: {e}")
        
        # 去重
        self.ips = list(set(self.ips))
        print(f"[*] 样本生成完毕，总计待测抽样 IP：{len(self.ips)} 个")

    def test_latency(self, ip):
        """测试连接延迟 (TCP Connect)"""
        try:
            start = time.perf_counter()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(TEST_TIMEOUT)
                # 尝试建立握手
                result = s.connect_ex((ip, TEST_PORT))
                if result == 0:
                    latency = (time.perf_counter() - start) * 1000
                    return {"ip": ip, "latency": int(latency)}
        except:
            pass
        return None

    def run(self):
        self.generate_ips()
        if not self.ips:
            print("[!] IP 列表为空，请检查配置")
            return

        print(f"[*] 开始测速 (并发线程: {MAX_THREADS})...")
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
            # 提交任务
            future_to_ip = {executor.submit(self.test_latency, ip): ip for ip in self.ips}
            
            completed = 0
            for future in as_completed(future_to_ip):
                res = future.result()
                if res:
                    self.results.append(res)
                
                completed += 1
                if completed % 200 == 0:
                    print(f"    进度: {completed}/{len(self.ips)} (已发现可用: {len(self.results)})")

        # 按延迟排序（从小到大）
        self.results.sort(key=lambda x: x['latency'])
        
        duration = int(time.time() - start_time)
        print(f"[*] 测速完成，耗时 {duration} 秒，共发现 {len(self.results)} 个可用节点")
        self.save_results()

    def save_results(self):
        """按照要求的格式保存优选结果"""
        count = min(len(self.results), TOP_NODES)
        if count == 0:
            print("[!] 未发现任何可用节点，请确认网络环境或更换测试端口")
            return

        try:
            with open(TXT_OUTPUT_FILE, "w", encoding="utf-8") as f:
                for i in range(count):
                    node = self.results[i]
                    # 格式：IP#jp 【日本】 JP
                    f.write(f"{node['ip']}#jp 【日本】 JP\n")
            
            print(f"[*] 优选结果已保存至 {TXT_OUTPUT_FILE}")
            print("-" * 30)
            print(f"延迟最低的前 {min(5, count)} 个节点预览：")
            for i in range(min(5, count)):
                print(f"  {i+1}. {self.results[i]['ip']} | {self.results[i]['latency']}ms")
        except Exception as e:
            print(f"[!] 保存文件出错: {e}")

if __name__ == "__main__":
    scanner = IPScannerJP()
    try:
        scanner.run()
    except KeyboardInterrupt:
        print("\n[!] 用户强制停止")
    except Exception as e:
        print(f"\n[!] 程序运行出错: {e}")
