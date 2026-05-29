import socket
import re
import time
import threading
import ipaddress
from queue import Queue

# ================= 配置参数 =================
TEST_TIMEOUT = 1.0   # GitHub Runner 网络较快，1秒足以判断是否为优选
TEST_PORT = 443      
MAX_THREADS = 50     # GitHub Actions 建议不要超过 50 线程，防止被限制
TOP_NODES = 20       
TXT_OUTPUT_FILE = "HK.txt"

# Cloudflare 官方 IPv4 网段
CF_IPV4_RANGES = [
    '173.245.48.0/20', '103.21.244.0/22', '103.22.200.0/22',
    '103.31.4.0/22', '141.101.64.0/18', '108.162.192.0/18',
    '190.93.240.0/20', '188.114.96.0/20', '197.234.240.0/22',
    '198.41.128.0/17', '162.158.0.0/15', '104.16.0.0/12',
    '172.64.0.0/13', '131.0.72.0/22'
]

class CloudflareNodeTester:
    def __init__(self):
        self.nodes = set()
        self.results = []
        self.lock = threading.Lock()
    
    def fetch_known_nodes(self):
        print(f"[*] 正在解析官方网段...")
        for cidr in CF_IPV4_RANGES:
            try:
                net = ipaddress.ip_network(cidr)
                if net.num_addresses <= 1024:
                    step = 8
                elif net.num_addresses <= 65536:
                    step = 256
                else:
                    step = 1024
                
                for i in range(1, net.num_addresses, step):
                    self.nodes.add(str(net[i]))
            except:
                continue
        print(f"[*] 样本生成完毕: {len(self.nodes)} 个待测节点")

    def test_node_speed(self, ip):
        try:
            start_time = time.time()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(TEST_TIMEOUT)
                result = s.connect_ex((ip, TEST_PORT))
                if result == 0:
                    latency = (time.time() - start_time) * 1000
                    return {'ip': ip, 'reachable': True, 'latency': int(latency)}
        except:
            pass
        return {'ip': ip, 'reachable': False}

    def worker(self, queue):
        while not queue.empty():
            ip = queue.get()
            result = self.test_node_speed(ip)
            if result['reachable']:
                with self.lock:
                    self.results.append(result)
            queue.task_done()

    def run(self):
        self.fetch_known_nodes()
        task_queue = Queue()
        for ip in self.nodes:
            task_queue.put(ip)
        
        print(f"[*] 开始测速...")
        threads = []
        for _ in range(MAX_THREADS):
            t = threading.Thread(target=self.worker, args=(task_queue,))
            t.daemon = True 
            t.start()
            threads.append(t)
        
        task_queue.join()
        
        sorted_nodes = sorted(self.results, key=lambda x: x['latency'])
        self.save_results(sorted_nodes)

    def save_results(self, results):
        count = min(len(results), TOP_NODES)
        with open(TXT_OUTPUT_FILE, 'w', encoding='utf-8') as f:
            for i in range(count):
                node = results[i]
                f.write(f"{node['ip']}#hk 【中国香港】 HK\n")
        print(f"[*] 结果已保存至 {TXT_OUTPUT_FILE}")

if __name__ == "__main__":
    CloudflareNodeTester().run()        
        # 按延迟从低到高排序
        sorted_nodes = sorted(self.results, key=lambda x: x['latency'])
        self.save_results(sorted_nodes)
        print(f"[*] 全程耗时: {int(time.time() - start_time)} 秒")

    def save_results(self, results):
        """保存为指定的 HK 格式"""
        count = min(len(results), TOP_NODES)
        try:
            with open(TXT_OUTPUT_FILE, 'w', encoding='utf-8') as f:
                for i in range(count):
                    node = results[i]
                    # 格式：IP#hk 【中国香港】 HK
                    f.write(f"{node['ip']}#hk 【中国香港】 HK\n")
            print(f"[*] 优选完成，结果已保存至 {TXT_OUTPUT_FILE}")
            
            # 屏幕打印前5个最快的结果
            for i in range(min(5, count)):
                print(f"优选: {results[i]['ip']} ({results[i]['latency']}ms)")
        except Exception as e:
            print(f"[!] 保存文件失败: {e}")

if __name__ == "__main__":
    try:
        tester = CloudflareNodeTester()
        tester.run()
    except KeyboardInterrupt:
        print("\n[!] 用户手动停止")
    except Exception as e:
        print(f"[!] 程序异常: {e}")        # 这些IP看起来是Cloudflare的IP地址
        octets = ip.split('.')
        if octets[0] == '104' and octets[1] == '18':
            return '美国'  # Cloudflare US IPs
        elif octets[0] == '108' and octets[1] == '162':
            return '美国'  # Cloudflare US IPs
        elif octets[0] == '162' and octets[1] == '159':
            return '美国'  # Cloudflare US IPs
        elif octets[0] == '172' and octets[1] == '64':
            return '美国'  # Cloudflare US IPs
        
        return '未知'
    except Exception as e:
        print(f"IP验证错误 {ip}: {str(e)}")
        return '未知'

def clean_ip(ip_str):
    """清理IP字符串，移除可能的冒号或其他字符"""
    # 移除末尾的冒号和空格
    ip_str = ip_str.strip().rstrip(':')
    # 验证是否为有效的IPv4地址
    pattern = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'
    if re.match(pattern, ip_str):
        # 进一步验证每个数字是否在0-255范围内
        parts = ip_str.split('.')
        if all(0 <= int(part) <= 255 for part in parts):
            return ip_str
    return None

# Cloudflare节点测试类
class CloudflareNodeTester:
    def __init__(self):
        self.nodes = set()  # 存储节点IP，使用set避免重复
        self.results = []   # 存储测试结果
        self.lock = threading.Lock()
    
    def fetch_known_nodes(self):
        """从公开来源获取已知的Cloudflare节点IP"""

        # 已更新为Cloudflare官方全量IPv4网段
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
            '104.24.0.0/14',
            '172.64.0.0/13',
            '131.0.72.0/22'
        ]
        
        # 从IP段生成部分IP示例
        for ip_range in ip_ranges:
            base_ip, cidr = ip_range.split('/')
            octets = base_ip.split('.')
            
            # 生成该网段的一些示例IP
            for i in range(1, 20):  # 每个网段生成19个示例IP
                ip = f"{octets[0]}.{octets[1]}.{octets[2]}.{i + int(octets[3])}"
                self.nodes.add(ip)
        
    
    def test_node_speed(self, ip):
        """测试单个节点的连接速度"""
        try:
            start_time = time.time()
            # 创建socket连接
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(TEST_TIMEOUT)
                result = s.connect_ex((ip, TEST_PORT))
                if result == 0:  # 连接成功
                    response_time = (time.time() - start_time) * 1000  # 转换为毫秒
                    return {
                        'ip': ip,
                        'reachable': True,
                        'response_time_ms': int(response_time),
                        'timestamp': datetime.now().isoformat()
                    }
                else:
                    return {
                        'ip': ip,
                        'reachable': False,
                        'response_time_ms': None,
                        'timestamp': datetime.now().isoformat()
                    }
        except Exception as e:
            return {
                'ip': ip,
                'reachable': False,
                'response_time_ms': None,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def worker(self, queue):
        """线程工作函数"""
        while not queue.empty():
            ip = queue.get()
            try:
                result = self.test_node_speed(ip)
                with self.lock:
                    self.results.append(result)
                    # 每完成360个测试，打印进度
                    if len(self.results) % 360 == 0:
                        print(f"已测试 {len(self.results)}/{len(self.nodes)} 个")
            finally:
                queue.task_done()
    
    def test_all_nodes(self):
        """测试所有节点的速度"""

        
        # 创建任务队列
        queue = Queue()
        for ip in self.nodes:
            queue.put(ip)
        
        # 启动线程
        threads = []
        for _ in range(min(MAX_THREADS, len(self.nodes))):
            thread = threading.Thread(target=self.worker, args=(queue,))
            thread.start()
            threads.append(thread)
        
        # 等待所有线程完成
        for thread in threads:
            thread.join()
        

    
    def sort_and_display_results(self):
        """排序并显示测试结果，包含中文国家信息"""
        # 过滤出可连接的节点并按响应时间排序
        reachable_nodes = [
            node for node in self.results 
            if node['reachable'] and node['response_time_ms'] is not None
        ]
        
        # 按响应时间升序排序(最快的在前)
        sorted_nodes = sorted(
            reachable_nodes, 
            key=lambda x: x['response_time_ms']
        )
        
        
        # 显示前N个最快节点，包含中文国家信息
        for i, node in enumerate(sorted_nodes[:TOP_NODES], 1):
            country = get_ip_country(node['ip'])
            print(f"{node['ip']}#hk 【中国香港】 HK")
        
        return sorted_nodes
    
    def save_results(self, results):
        """只保存前30名结果到TXT文件，并显示中文国家信息"""
        try:
            # 只取前30名结果
            top_results = results[:20]  # 明确只取前30名
            
            with open(TXT_OUTPUT_FILE, 'w', encoding='utf-8') as f:
                # 清空文件并只写入前30个结果
                for i, node in enumerate(top_results):
                    # 获取IP的国家信息（已经是中文）
                    country = get_ip_country(node['ip'])
                    line = f"{node['ip']}#hk 【中国香港】 HK\n"
                    f.write(line)
            
        except Exception as e:
            print(f"保存结果失败: {e}")

# IP地理位置查询功能
def batch_query_ip_countries():
    """批量查询IP地址的国家信息(显示中文)"""
    print("\n===== IP地址国家信息批量查询 =====")
    
    # 从cf_IP.txt文件读取IP地址列表
    try:
        with open(TXT_OUTPUT_FILE, 'r', encoding='utf-8') as f:
            ip_list = []
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and not line.startswith('=') and ':' in line:
                    # 从格式 "IP:端口#备注" 中提取IP
                    ip = line.split(':')[0].strip()
                    ip_list.append(ip)
                elif line and not line.startswith('#') and not line.startswith('=') and ' ' not in line and '.' in line:
                    # 纯IP地址行
                    ip_list.append(line)
        print(f"从文件读取了 {len(ip_list)} 个IP地址")
    except Exception as e:
        print(f"无法从文件读取IP: {str(e)}")
        print("使用默认IP列表进行演示")
        # 默认IP列表
        ip_list = [
            "108.162.192.3", "108.162.192.7", "108.162.192.4", "108.162.192.9",
            "162.159.0.4", "162.159.0.1", "162.159.0.3", "108.162.192.2"
        ]
    
    # 清理并验证IP地址列表
    cleaned_ips = []
    for ip in ip_list:
        cleaned_ip = clean_ip(ip)
        if cleaned_ip:
            cleaned_ips.append(cleaned_ip)
        else:
            print(f"无效的IP地址: {ip}")
    
    print(f"清理后有效IP地址数量: {len(cleaned_ips)}")
    
    # 获取每个IP的国家信息（已经是中文）
    results = []
    for i, ip in enumerate(cleaned_ips):
        print(f"正在查询 {i+1}/{len(cleaned_ips)}: {ip}")
        country = get_ip_country(ip)
        results.append(f"{ip} {country}")
        
        # 添加足够的延迟以避免API请求过于频繁
        if i < len(cleaned_ips) - 1:
            time.sleep(3)  # 增加延迟到3秒
    
    # 将结果写入文件
    # 注意：这里原代码中 IP_COUNTRIES_FILE 未定义，建议根据需要手动补充或使用 TXT_OUTPUT_FILE
    # 为了保持代码不被大幅修改，此处暂不添加变量定义。
    
    print(f"处理的IP地址总数: {len(results)}")
    print("===================================")

# Cloudflare节点测试功能
def test_cloudflare_nodes():
    """运行Cloudflare节点测试"""
    print("\n===== Cloudflare节点测速工具 =====")
    tester = CloudflareNodeTester()
    tester.run()

# CloudflareNodeTester类的run方法
def run_cloudflare_tester(self):
    """运行整个测试流程"""
    start_time = time.time()
    
    # 1. 获取节点
    self.fetch_known_nodes()
    
    # 2. 测试所有节点
    self.test_all_nodes()
    
    # 3. 排序并显示结果
    sorted_nodes = self.sort_and_display_results()
    
    # 4. 保存结果
    self.save_results(sorted_nodes)
    
    total_time = int(time.time() - start_time)

# 添加run方法到CloudflareNodeTester类
CloudflareNodeTester.run = run_cloudflare_tester

# 主函数 - 直接执行Cloudflare节点测试
if __name__ == "__main__":

    try:
        # 直接执行Cloudflare节点测试
        tester = CloudflareNodeTester()
        tester.run()
        
    except KeyboardInterrupt:
        print("\n用户中断了程序")
    except Exception as e:
        print(f"程序出错: {e}")
