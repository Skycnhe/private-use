import socket
import time
import threading
import ipaddress
import requests
from queue import Queue

# ================= 配置参数 =================
TEST_TIMEOUT = 1.0       # 延迟测试超时(秒)
TEST_PORT = 443          # 测试端口
MAX_THREADS = 100        # 并发线程数
TARGET_COUNT = 50        # 目标：收集多少个台湾IP后停止
TARGET_COUNTRY = "TW"     # 目标国家代码
TXT_OUTPUT_FILE = "TW.txt" 

# Cloudflare 官方 IPv4 网段
CF_IPV4_RANGES = [
    '173.245.48.0/20', '103.21.244.0/22', '103.22.200.0/22',
    '103.31.4.0/22', '141.101.64.0/18', '108.162.192.0/18',
    '190.93.240.0/20', '188.114.96.0/20', '197.234.240.0/22',
    '198.41.128.0/17', '162.158.0.0/15', '104.16.0.0/12',
    '172.64.0.0/13', '131.0.72.0/22'
]

def get_real_location(ip):
    """通过API识别IP归属地"""
    try:
        # 使用 ip-api.com 免费接口 (每分钟限45次请求)
        url = f"http://ip-api.com/json/{ip}?fields=status,countryCode"
        resp = requests.get(url, timeout=5).json()
        if resp.get('status') == 'success':
            return resp.get('countryCode')
        return "Unknown"
    except:
        return "Error"

class CloudflareTWScanner:
    def __init__(self):
        self.nodes = set()
        self.results = []
        self.lock = threading.Lock()
    
    def fetch_nodes(self):
        """生成待测样本"""
        print("[*] 正在解析全量网段样本...")
        for cidr in CF_IPV4_RANGES:
            try:
                net = ipaddress.ip_network(cidr)
                # 根据网段大小智能采样，确保覆盖范围广
                if net.num_addresses <= 1024:
                    step = 8
                elif net.num_addresses <= 65536:
                    step = 128
                else:
                    step = 512
                
                for i in range(1, net.num_addresses, step):
                    self.nodes.add(str(net[i]))
            except:
                continue
        print(f"[*] 样本生成完毕: {len(self.nodes)} 个候选节点")

    def test_latency(self, ip):
        """测试连接延迟"""
        try:
            start_time = time.time()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(TEST_TIMEOUT)
                if s.connect_ex((ip, TEST_PORT)) == 0:
                    return int((time.time() - start_time) * 1000)
        except:
            pass
        return None

    def worker(self, queue):
        while not queue.empty():
            ip = queue.get()
            ms = self.test_latency(ip)
            if ms:
                with self.lock:
                    self.results.append({'ip': ip, 'ms': ms})
            queue.task_done()

    def run(self):
        self.fetch_nodes()
        q = Queue()
        for ip in self.nodes:
            q.put(ip)

        print(f"[*] 第一步：正在全球节点中筛选低延迟IP (线程: {MAX_THREADS})...")
        threads = []
        for _ in range(MAX_THREADS):
            t = threading.Thread(target=self.worker, args=(q,))
            t.daemon = True
            t.start()
            threads.append(t)
        
        q.join()
        
        # 按延迟排序（最快的排在前面）
        sorted_nodes = sorted(self.results, key=lambda x: x['ms'])
        
        print(f"[*] 第二步：正在从低延迟节点中筛选 {TARGET_COUNTRY} 归属地...")
        final_tw_list = []
        count = 0
        
        for node in sorted_nodes:
            if count >= TARGET_COUNT:
                break
                
            code = get_real_location(node['ip'])
            
            if code == TARGET_COUNTRY:
                count += 1
                node['code'] = code.lower()
                node['label'] = "中国台湾"
                final_tw_list.append(node)
                print(f"  [+] 命中台湾节点 #{count}: {node['ip']} ({node['ms']}ms)")
            
            # 关键：遵守免费API频率限制 (1.35秒一次请求，约每分钟44次)
            # 如果你有付费IP库或API，可以移除此延迟
            time.sleep(1.35) 

        if final_tw_list:
            self.save(final_tw_list)
        else:
            print("[!] 扫描完成，但在样本中未发现台湾节点。")

    def save(self, data):
        with open(TXT_OUTPUT_FILE, 'w', encoding='utf-8') as f:
            for n in data:
                # 按照 IP#code 【国家】 地区代码 格式输出
                line = f"{n['ip']}#{n['code']} 【{n['label']}】 {n['code'].upper()}\n"
                f.write(line)
        print(f"[*] 成功！已将 {len(data)} 个台湾节点保存至 {TXT_OUTPUT_FILE}")

if __name__ == "__main__":
    try:
        scanner = CloudflareTWScanner()
        scanner.run()
    except KeyboardInterrupt:
        print("\n[!] 用户停止任务")
    except Exception as e:
        print(f"[!] 程序异常: {e}")
