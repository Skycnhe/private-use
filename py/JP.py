import socket
import time
import ipaddress
from concurrent.futures import ThreadPoolExecutor, as_completed

# ================= 配置参数 =================
TEST_TIMEOUT = 1.0     # 连接超时时间（秒）
TEST_PORT = 443        # 测试端口（通常为 443 或 80）
MAX_THREADS = 200      # 并发线程数
TOP_NODES = 30         # 最终保留的优选数量
TXT_OUTPUT_FILE = "JP.txt"

# 筛选出的日本方向（中国优化线路）典型 IP 段
# 包含 AWS Tokyo, GCP Tokyo, Oracle Tokyo 以及部分软银/IIJ 常用段
TARGET_RANGES = [
    # --- AWS Tokyo (部分段中国联通/电信直连较好) ---
    '13.112.0.0/14', '18.176.0.0/14', '52.192.0.0/14', '54.248.0.0/15', '3.112.0.0/14',
    
    # --- GCP Tokyo (Google Cloud 日本，联通延迟极低) ---
    '34.84.0.0/16', '35.200.0.0/16', '34.146.0.0/16',
    
    # --- Oracle Japan (甲骨文东京/大阪，热门优化段) ---
    '158.101.64.0/18', '129.150.0.0/15', '130.162.0.0/16', '193.122.0.0/15',
    
    # --- Microsoft Azure Japan ---
    '13.71.0.0/16', '20.40.0.0/14',
    
    # --- Fastly / Akamai 日本节点 (您之前关注的段) ---
    '151.101.108.0/22', '146.75.112.0/22', '157.185.128.0/18',
    
    # --- 典型 Softbank/IIJ 线路段 (部分 VPS 厂商常用) ---
    '103.156.184.0/24', '45.125.0.0/16', '118.238.0.0/16', '202.221.0.0/16'
]

class IPScannerJP:
    def __init__(self):
        self.ips = []
        self.results = []

    def generate_ips(self):
        """解析目标网段，采用智能步长采样以覆盖更多网段"""
        print("[*] 正在解析日本优化网段...")
        for cidr in TARGET_RANGES:
            try:
                network = ipaddress.ip_network(cidr)
                # 采样策略：根据网段大小调整步长
                # 小于 /24：全测 (step=1)
                # /24 到 /20：每隔 16 个测一个
                # 大于 /20：大跨度扫描
                if network.num_addresses <= 256:
                    step = 2
                elif network.num_addresses <= 4096:
                    step = 32
                else:
                    step = 128
                
                for i in range(0, network.num_addresses, step):
                    self.ips.append(str(network[i]))
            except:
                continue
        
        self.ips = list(set(self.ips))
        print(f"[*] 样本生成完毕，总计待测抽样 IP：{len(self.ips)} 个")

    def test_latency(self, ip):
        """测试 TCP 连接延迟"""
        try:
            start = time.perf_counter()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(TEST_TIMEOUT)
                if s.connect_ex((ip, TEST_PORT)) == 0:
                    latency = (time.perf_counter() - start) * 1000
                    return {"ip": ip, "latency": int(latency)}
        except:
            pass
        return None

    def run(self):
        self.generate_ips()
        if not self.ips: return

        print(f"[*] 开始对中国优化线路进行测速 (线程: {MAX_THREADS})...")
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
                    print(f"    进度: {completed}/{len(self.ips)} (已发现: {len(self.results)})")

        self.results.sort(key=lambda x: x['latency'])
        
        print(f"[*] 测速完成，共发现 {len(self.results)} 个响应节点")
        self.save_results()

    def save_results(self):
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
            
            print(f"[*] 优选结果已保存至 {TXT_OUTPUT_FILE}")
            for i in range(min(5, count)):
                print(f"  {i+1}. {self.results[i]['ip']} - {self.results[i]['latency']}ms")
        except Exception as e:
            print(f"[!] 保存失败: {e}")

if __name__ == "__main__":
    scanner = IPScannerJP()
    try:
        scanner.run()
    except KeyboardInterrupt:
        print("\n[!] 停止")        if count == 0:
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
