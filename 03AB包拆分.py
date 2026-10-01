import os
import shutil


def format_size(size_in_bytes):
    """将字节大小格式化为易读的 MB/GB 单位"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.2f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.2f} PB"


def partition_files_ordered(all_files, k=4):
    """按原始文件名顺序，将文件列表连续切分为 k 份，使每份总体积最接近平均值"""
    total_size = sum(size for _, size in all_files)
    num_files = len(all_files)

    # 文件数量比目标文件夹少时的特殊处理
    if num_files <= k:
        chunks = [[f] for f in all_files]
        while len(chunks) < k:
            chunks.append([])
        return chunks

    buckets = [[] for _ in range(k)]
    curr_bucket = 0
    cum_size = 0

    for i, (fpath, fsize) in enumerate(all_files):
        remaining_files = num_files - i
        remaining_buckets = k - 1 - curr_bucket

        # 保证后续每个桶至少能分到 1 个文件
        if remaining_files == remaining_buckets:
            curr_bucket += 1
            buckets[curr_bucket].append((fpath, fsize))
            cum_size += fsize
            continue

        if curr_bucket < k - 1:
            # 当前桶的目标累加体积 (1/4, 2/4, 3/4 ...)
            target_cum_size = (curr_bucket + 1) * (total_size / k)

            dist_current = abs(cum_size - target_cum_size)
            dist_if_added = abs((cum_size + fsize) - target_cum_size)

            # 如果加上当前文件后偏离目标更远，且当前桶不为空，则切分到下一个桶
            if (
                len(buckets[curr_bucket]) > 0
                and dist_if_added > dist_current
                and (cum_size + fsize) > target_cum_size
            ):
                curr_bucket += 1

        buckets[curr_bucket].append((fpath, fsize))
        cum_size += fsize

    return buckets


def distribute_assetbundle_ordered():
    # 1. 定位当前脚本所在目录与目标路径
    base_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.join(base_dir, "AssetBundle")
    target_names = ["a1", "a2", "a3", "a4"]
    target_dirs = [os.path.join(base_dir, name) for name in target_names]

    # 检查 AssetBundle 文件夹是否存在
    if not os.path.exists(src_dir):
        print(f"❌ 错误：未在当前目录下找到 [{src_dir}] 文件夹！")
        return

    print("🚀 开始初始化目标文件夹...")

    # 3. 处理目标文件夹：存在则清空，不存在则创建
    for t_dir in target_dirs:
        if os.path.exists(t_dir):
            print(f"正在清空已有文件夹: {os.path.basename(t_dir)}")
            shutil.rmtree(t_dir)
        os.makedirs(t_dir, exist_ok=True)

    # 扫描 AssetBundle 中的所有文件
    print("📦 正在扫描 AssetBundle 中的所有文件...")
    all_files = []
    for root, _, files in os.walk(src_dir):
        for file in files:
            full_path = os.path.join(root, file)
            try:
                size = os.path.getsize(full_path)
                # 保存相对路径和大小
                rel_path = os.path.relpath(full_path, src_dir)
                all_files.append((full_path, rel_path, size))
            except Exception as e:
                print(f"⚠ 无法读取文件大小 [{full_path}]: {e}")

    if not all_files:
        print("⚠️ AssetBundle 文件夹中没有可复制的文件！")
        return

    # 严格保持文件名/相对路径的自然顺序排序
    all_files.sort(key=lambda x: x[1])

    # 2. 连续区间切分（按顺序分块）
    files_with_size_only = [(item[0], item[2]) for item in all_files]
    partitioned_buckets = partition_files_ordered(
        files_with_size_only, k=len(target_dirs)
    )

    print(
        f"🚚 找到 {len(all_files)} 个文件，按顺序切分为 4 个区间开始复制..."
    )

    # 挨个区间复制到对应的 a1, a2, a3, a4 文件夹中
    for bucket_idx, bucket_files in enumerate(partitioned_buckets):
        t_dir = target_dirs[bucket_idx]
        t_name = target_names[bucket_idx]
        total_bucket_size = sum(s for _, s in bucket_files)

        for src_path, fsize in bucket_files:
            rel_path = os.path.relpath(src_path, src_dir)
            dst_path = os.path.join(t_dir, rel_path)

            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            shutil.copy2(src_path, dst_path)

        size_str = format_size(total_bucket_size)
        print(
            f"✅ 文件夹 [{t_name}]: 分配了 {len(bucket_files)} 个文件 | 总大小 = {size_str}"
        )

    print("\n🎉 所有文件已按原始名称顺序成功分配完成！")


if __name__ == "__main__":
    distribute_assetbundle_ordered()