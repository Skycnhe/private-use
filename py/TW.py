import socket
import re
import time
import threading
import requests
from queue import Queue
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ================= 配置参数 =================
TEST_TIMEOUT = 3       # 测试超时时间(秒)
TEST_PORT = 443        # 测试端口
MAX_THREADS = 50       # 最大线程数 (建议设为20-50以加快扫描速度)
TOP_NODES = 20         # 显示和保存前N个最快节点
TXT_OUTPUT_FILE = "TW.txt"    # 结果保存文件
IP_COUNTRIES_FILE = "ip_countries.txt" # 批量查询结果文件

# ================= 国家代码映射 =================
COUNTRY_CODES = {
    'US': '美国', 'CN': '中国', 'JP': '日本', 'SG': '新加坡',
    'KR': '韩国', 'GB': '英国', 'FR': '法国', 'DE': '德国',
    'AU': '澳大利亚', 'CA': '加拿大', 'HK': '中国香港',
    'TW': '中国台湾', 'IN': '印度', 'RU': '俄罗斯',
    'BR': '巴西', 'MX': '墨西哥', 'NL': '荷兰',
    'SE': '瑞典', 'CH': '瑞士', 'IT': '意大利',
    'ES': '西班牙', 'Unknown': '未知'
}

# ================= 辅助函数 =================
def get_ip_country(ip):
    """获取IP地址对应的国家信息(返回中文)"""
    try:
        # 简单的本地判断：如果是扫描列表里的IP，通常就是台湾
        # 为了节省API请求，这里可以做一个快速判断，但为了准确性保留API查询
        pass 

        session = requests.Session()
        retry = Retry(total=2, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        # 尝试 ip-api.com (速度快，限制少)
        try:
            url = f"http://ip-api.com/json/{ip}?fields=countryCode,country"
            response = session.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                code = data.get('countryCode')
                if code == 'TW': return '中国台湾'
                if code == 'HK': return '中国香港'
                if code == 'JP': return '日本'
                if code == 'US': return '美国'
                return COUNTRY_CODES.get(code, data.get('country', '未知'))
        except:
            pass
            
        return '中国台湾' # 如果API失败，鉴于我们扫描的是台湾段，默认返回台湾
    except Exception:
        return '未知'

def clean_ip(ip_str):
    """清理IP字符串"""
    ip_str = ip_str.strip().rstrip(':')
    pattern = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'
    if re.match(pattern, ip_str):
        parts = ip_str.split('.')
        if all(0 <= int(part) <= 255 for part in parts):
            return ip_str
    return None

# ================= 主测试类 =================
class CloudflareNodeTester:
    def __init__(self):
        self.nodes = set()
        self.results = []
        self.lock = threading.Lock()
    
    def fetch_known_nodes(self):
        """生成常驻台湾的Cloudflare节点IP"""
        print(f"正在生成扫描列表...")
        
        # === 台湾优化网段 (TPE/KHH) ===
        ip_ranges = [
            # 172.69.x.x 系列 (常见于台北 TPE)
            '172.69.221.0/24', 
            '172.69.184.0/24',
            
            # 172.71.x.x 系列 (常见于高雄 KHH)
            '172.71.139.0/24',
            '172.71.204.0/24',
            
            # 其他常驻台湾段
            '172.68.87.0/24',
            '172.68.106.0/24',
            '162.158.240.0/24',
            '104.29.64.0/24'
        ]
        
        for ip_range in ip_ranges:
            try:
                base_ip, cidr = ip_range.split('/')
                octets = base_ip.split('.')
                
                # 策略：扫描每个网段的 .1 到 .25 (通常网关和活跃节点在前部)
                # 如果需要更深度的扫描，可以把 range(1, 26) 改大，例如 range(1, 50)
                for i in range(1, 26): 
                    ip = f"{octets[0]}.{octets[1]}.{octets[2]}.{i}"
                    self.nodes.add(ip)
            except Exception as e:
                print(f"解析网段 {ip_range} 出错: {e}")
                
        print(f"共生成 {len(self.nodes)} 个待测 IP")
    
    def test_node_speed(self, ip):
        """测试Socket连接延迟"""
        try:
            start_time = time.time()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(TEST_TIMEOUT)
                result = s.connect_ex((ip, TEST_PORT))
                if result == 0:
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
        while not queue.empty():
            ip = queue.get()
            try:
                result = self.test_node_speed(ip)
                if result['reachable']:
                    with self.lock:
                        self.results.append(result)
                        # 实时显示发现的低延迟节点
                        if result['response_time_ms'] < 100:
                            print(f"发现可用节点: {result['ip']} ({result['response_time_ms']}ms)")
            finally:
                queue.task_done()
    
    def test_all_nodes(self):
        """多线程执行测试"""
        queue = Queue()
        for ip in self.nodes:
            queue.put(ip)
        
        print(f"启动 {MAX_THREADS} 个线程进行测速...")
        threads = []
        for _ in range(min(MAX_THREADS, len(self.nodes))):
            thread = threading.Thread(target=self.worker, args=(queue,))
            thread.daemon = True
            thread.start()
            threads.append(thread)
        
        for thread in threads:
            thread.join()
    
    def sort_and_display_results(self):
        """排序并显示"""
        print(f"\n正在处理结果 (共找到 {len(self.results)} 个可用节点)...")
        
        # 按延迟排序
        sorted_nodes = sorted(
            self.results, 
            key=lambda x: x['response_time_ms']
        )
        
        print("\n===== 速度最快的前 10 个节点 =====")
        for node in sorted_nodes[:10]:
            print(f"IP: {node['ip']:<15} 延迟: {node['response_time_ms']}ms")
            
        return sorted_nodes
    
    def save_results(self, results):
        """保存结果到文件"""
        if not results:
            print("未找到可用节点，无法保存。")
            return

        try:
            top_results = results[:TOP_NODES]
            
            with open(TXT_OUTPUT_FILE, 'w', encoding='utf-8') as f:
                for node in top_results:
                    # 格式: IP#tw 【中国台湾】 TW
                    # 可以在这里调用 get_ip_country，但为了速度，既然我们扫的是台湾段，
                    # 这里直接写入固定的备注格式
                    line = f"{node['ip']}#tw 【中国台湾】 TW\n"
                    f.write(line)
            
            print(f"\n成功！前 {len(top_results)} 个最快节点已保存至: {TXT_OUTPUT_FILE}")
            
        except Exception as e:
            print(f"保存文件失败: {e}")

    def run(self):
        """执行完整流程"""
        start_time = time.time()
        
        self.fetch_known_nodes()
        if not self.nodes:
            print("没有IP可测，程序退出")
            return

        self.test_all_nodes()
        sorted_nodes = self.sort_and_display_results()
        self.save_results(sorted_nodes)
        
        duration = int(time.time() - start_time)
        print(f"\n全部完成，耗时 {duration} 秒。")

# ================= 主程序入口 =================
if __name__ == "__main__":
    try:
        tester = CloudflareNodeTester()
        tester.run()
        
        # 防止窗口立即关闭
        input("\n按回车键退出...")
        
    except KeyboardInterrupt:
        print("\n用户强制停止。")
    except Exception as e:
        print(f"发生错误: {e}")
        input("按回车键退出...")