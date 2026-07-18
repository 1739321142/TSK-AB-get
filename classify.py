import os
import shutil
from pathlib import Path

def classify_and_rename_assets():
    """
    1. 从 Assets/AssetBundles 递归复制指定文件到与 Assets 同级目录
    2. 对复制后的文件自动执行重命名：
       - .atlas.asset → .atlas
       - .skel.asset → .skel
    3. 若重命名目标已存在，则删除复制过来的文件
    4. 若原文件本身就是 .skel 和 .atlas，则直接复制，不触发重命名
    """
    # ====================== 第一部分：复制文件 ======================
    current_dir = Path.cwd()
    source_root = current_dir / "Assets" / "AssetBundles"
    target_root = current_dir  # 复制到与 Assets 同级的目录

    # 核心修改：在允许复制的后缀中加入 ".skel"
    target_suffixes = {".atlas.asset", ".png", ".skel.asset", ".atlas", ".json", ".skel"}
    exclude_endings = {"_Atlas.json", "_SkeletonData.json", "_Material.json", "Multiply.json"}

    # 检查源目录
    if not source_root.exists():
        print(f"❌ 错误：源目录 {source_root} 不存在，请检查路径！")
        return

    # 复制统计变量
    copied_count = 0
    overwritten_count = 0
    excluded_count = 0
    skipped_count = 0

    print("="*60)
    print(f"✅ 开始复制文件：{source_root} → {target_root}")
    print("="*60)

    try:
        # 1. 执行复制
        for file_path in source_root.rglob("*"):
            if file_path.is_file():
                file_name = file_path.name

                # 优先排除指定结尾的文件
                if any(file_name.endswith(ending) for ending in exclude_endings):
                    excluded_count += 1
                    print(f"🚫 排除【复制】：{file_path}")
                    continue

                # 检查是否为目标后缀
                if any(file_name.endswith(suffix) for suffix in target_suffixes):
                    relative_path = file_path.relative_to(source_root)
                    target_file = target_root / relative_path

                    # 确保目标目录存在
                    target_file.parent.mkdir(parents=True, exist_ok=True)

                    # 复制文件（保留元数据）
                    if target_file.exists():
                        shutil.copy2(file_path, target_file)
                        overwritten_count += 1
                        print(f"⚠️  覆盖【复制】：{file_path} → {target_file}")
                    else:
                        shutil.copy2(file_path, target_file)
                        copied_count += 1
                        print(f"✅ 成功【复制】：{file_path} → {target_file}")
                else:
                    skipped_count += 1

        # 输出复制统计
        print("\n" + "="*60)
        print("📦 复制阶段完成")
        print(f"   新复制文件数：{copied_count}")
        print(f"   覆盖文件数：  {overwritten_count}")
        print(f"   排除文件数：  {excluded_count}")
        print(f"   跳过文件数：  {skipped_count}")
        print("="*60)

        # ====================== 第二部分：重命名文件 ======================
        print("\n" + "="*60)
        print(f"🔄 开始对复制后的文件进行重命名")
        print("="*60)

        # 重命名规则（保持原样，.atlas 和 .skel 顺理成章不会被匹配，从而免受改名影响）
        rename_rules = {
            ".atlas.asset": ".atlas",
            ".skel.asset": ".skel"
        }

        # 重命名统计变量
        renamed_count = 0
        deleted_count = 0  
        rename_error_count = 0
        total_scanned = 0

        # 2. 执行重命名（仅扫描目标目录，跳过 Assets 源文件夹）
        for root, dirs, files in os.walk(target_root):
            # 关键：跳过 Assets 源目录，只处理复制出来的文件
            if "Assets" in Path(root).parts:
                continue

            for filename in files:
                total_scanned += 1
                file_path = os.path.join(root, filename)

                # 匹配重命名规则
                for old_suffix, new_suffix in rename_rules.items():
                    if filename.endswith(old_suffix):
                        try:
                            # 计算新文件名
                            new_filename = filename[:-len(old_suffix)] + new_suffix
                            new_file_path = os.path.join(root, new_filename)

                            # 检查是否已存在，若存在则删除复制的文件
                            if os.path.exists(new_file_path):
                                os.remove(file_path)
                                print(f"🗑️ 删除【复制文件】：{filename} (目标文件已存在)")
                                deleted_count += 1
                                continue

                            # 执行重命名
                            os.rename(file_path, new_file_path)
                            print(f"✅ 成功【重命名】：{filename} → {new_filename}")
                            renamed_count += 1
                            break

                        except PermissionError:
                            print(f"❌ 失败【操作】：{filename} (权限不足)")
                            rename_error_count += 1
                            break
                        except Exception as e:
                            print(f"❌ 失败【操作】：{filename} ({str(e)})")
                            rename_error_count += 1
                            break

        # 输出重命名统计
        print("\n" + "="*60)
        print("🏁 全部任务完成")
        print(f"   重命名扫描文件数：{total_scanned}")
        print(f"   成功重命名数：    {renamed_count}")
        print(f"   删除复制文件数：  {deleted_count}")
        print(f"   操作失败数：      {rename_error_count}")
        print("="*60)

    except Exception as e:
        print(f"\n❌ 程序执行出错：{str(e)}")

if __name__ == "__main__":
    try:
        classify_and_rename_assets()
    except KeyboardInterrupt:
        print("\n\n⚠️  用户手动中断了程序执行")
    except Exception as e:
        print(f"\n❌  程序执行出错：{str(e)}")
    finally:
        input("\n按回车键退出程序...")