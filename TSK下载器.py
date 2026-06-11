import os
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 配置参数 ---
CATALOG_FILE = "catalog.json"
TARGET_DIR = "AssetBundle"
URL_LIST_FILE = "C地址.txt"
BASE_URL = "https://d3mya90gbacu0m.cloudfront.net/prod/StreamingAssets/aa/WebGL/"
MAX_WORKERS = 8  # 多线程数量

def clean_temp_files():
    """清理由于程序意外关闭遗留下的临时文件"""
    if not os.path.exists(TARGET_DIR):
        return
    for filename in os.listdir(TARGET_DIR):
        if filename.endswith(".tmp"):
            tmp_path = os.path.join(TARGET_DIR, filename)
            try:
                os.remove(tmp_path)
                print(f"[*] 已清理残留的临时文件: {filename}")
            except Exception:
                pass

def extract_bundle_names():
    """极限速度：纯 C 底层字符串分割法（无正则）"""
    if not os.path.exists(CATALOG_FILE):
        print(f"[错误] 在同级目录下找不到 {CATALOG_FILE} 文件！")
        return []

    print("[*] 正在解析 catalog.json (已启用纯字符分割极速模式)...")
    start_time = time.time()
    
    bundles = set()
    
    # 直接以二进制全量读入内存
    with open(CATALOG_FILE, 'rb') as f:
        content = f.read()
        
    parts = content.split(b'.bundle')
    
    for part in parts[:-1]:
        p1 = part.rfind(b'/')
        p2 = part.rfind(b'\\')
        p3 = part.rfind(b'"')
        
        start_idx = max(p1, p2, p3) + 1
        bundle_bytes = part[start_idx:] + b'.bundle'
        
        try:
            bundles.add(bundle_bytes.decode('utf-8'))
        except Exception:
            pass

    elapsed_time = time.time() - start_time
    print(f"[*] 解析彻底完成！提取了 {len(bundles)} 个文件，耗时: {elapsed_time:.4f} 秒。")
    return list(bundles)

def save_urls_to_file(bundles):
    """将拼接完整的地址统一输出到 C地址.txt 中"""
    if not bundles:
        return
    try:
        with open(URL_LIST_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join([BASE_URL + bundle for bundle in bundles]))
        print(f"[*] 成功！所有解析出的完整地址已输出至: {URL_LIST_FILE}")
    except Exception as e:
        print(f"[警告] 写入地址文件失败: {e}")

def download_bundle(bundle_name):
    """单线程下载函数：加入无限重试机制"""
    url = BASE_URL + bundle_name
    final_path = os.path.join(TARGET_DIR, bundle_name)
    tmp_path = final_path + ".tmp"

    # 如果正式文件已存在，直接跳过
    if os.path.exists(final_path):
        return f"[跳过] {bundle_name} 已存在。"

    attempt = 1  # 记录尝试次数
    
    # 开始无限循环，直到成功才 return 退出
    while True:
        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status() 

            with open(tmp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        f.write(chunk)

            # 彻底完成后重命名
            os.rename(tmp_path, final_path)
            
            # 如果重试过，在成功时带上重试次数提示
            if attempt > 1:
                return f"[成功] {bundle_name} 下载完成！(经过 {attempt} 次尝试)"
            else:
                return f"[成功] {bundle_name} 下载完成！"

        except Exception as e:
            # 下载出错时，清理本次产生的废弃临时文件
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except:
                    pass
            
            # 打印警告信息，方便你观察网络状况
            print(f"[警告] {bundle_name} 下载失败，正在进行第 {attempt + 1} 次重试... (报错: {e})")
            
            attempt += 1
            time.sleep(2)  # 暂停 2 秒后重试，避免在彻底断网时瞬间产生几万次无效请求拖死 CPU

def main():
    print("=== 开始运行资源提取与下载脚本 ===")
    
    if not os.path.exists(TARGET_DIR):
        os.makedirs(TARGET_DIR)
        print(f"[*] 已创建下载文件夹: {TARGET_DIR}")

    clean_temp_files()

    bundles = extract_bundle_names()
    if not bundles:
        print("[-] 未解析到任何文件，程序即将退出。")
        return

    save_urls_to_file(bundles)

    print(f"\n[*] 开始多线程并行下载 (当前并发线程数: {MAX_WORKERS})...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(download_bundle, bundle): bundle for bundle in bundles}
        
        for future in as_completed(futures):
            print(future.result())

    print("\n[*] 恭喜，所有任务已全部执行完毕！")

if __name__ == "__main__":
    main()