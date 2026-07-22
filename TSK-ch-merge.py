#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
通用 Spine 多部件融合脚本 (手部保护与武器隐藏修复版)
更新说明：
1. 关闭“皮肤转动画”功能，表情 Skin 完好保留在皮肤层。
2. 彻底保留所有原始插槽、骨骼、皮肤与动画数据。
3. 支持独立开关动作 (show_layer_图层名 / hide_layer_图层名)。
4. 支持排除指定图层的开关 (EXCLUDE_SWITCH_LAYERS, 如 m1)。
5. 支持多图层组合开关 (COMBINED_SWITCH_GROUPS, 如 f 和 b 做在一起)。
6. 新增：自动修复 weapon_0 等武器隐藏动作，过滤并保护手部插槽（hand/finger）不被误隐藏。
"""

import os
import re
import json
import subprocess

# ==========================================
# ⚙️ 模型参数配置区
# ==========================================
MODEL_CONFIG = {
    # 1. 文件名匹配规则 (正则)
    "FILE_PATTERN": r'^.*?_([a-zA-Z0-9]+)\.skel$', 
    
    # 2. 根骨骼名称
    "ROOT_BONE_NAME": "root",
    
    # 3. 忽略融合的图层标识
    "IGNORE_LAYERS": ["m0"],
    
    # 4. 图层融合优先级 (由下至上)
    "LAYER_PRIORITY": {'c': 0, 'b': 1, 'm1': 2, 'f': 3},
    
    # 5. 需要进行坐标预处理的图层
    "OFFSET_LAYER_NAME": "c",
    
    # 6. 预处理图层的 Y 轴偏移量
    "OFFSET_Y_VALUE": -800,
    
    # 7. 皮肤转动画开关 (已关闭：保持原始 Skins 结构)
    "CONVERT_SKINS_TO_ANIMS": False,

    # 8. 不自动生成开关动作的图层 (如 m1)
    "EXCLUDE_SWITCH_LAYERS": ["m1"],

    # 9. 组合开关配置 (将多个图层的开关合并为一个动作，例如 f 和 b 做在一起)
    "COMBINED_SWITCH_GROUPS": [
        ["f", "b"]  # 将 f 和 b 图层合并生成 show_layer_f_b / hide_layer_f_b
    ],

    # 10. 武器隐藏动作修复配置 (防止隐藏武器时把手也一起收掉)
    "WEAPON_HIDE_ANIM_NAMES": ["weapon_0"],     # 需排查手部误隐藏的动作关键字
    "HAND_SLOT_KEYWORDS": ["hand", "finger"],   # 识别为手/手指的插槽关键字 (忽略大小写)
}
# ==========================================

def load_skel_file(file_path):
    """读取 .skel 文件，自动调用工具转码"""
    with open(file_path, "rb") as f:
        header = f.read(2)
        f.seek(0)
        raw_bytes = f.read()

    is_binary = (len(header) > 0 and header[0] == 0x8a)
    if not is_binary:
        try:
            return json.loads(raw_bytes.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            is_binary = True

    if is_binary:
        json_file_path = os.path.splitext(file_path)[0] + ".json"
        if os.path.exists("SpineSkeletonDataConverter.exe"):
            print(f"  🔍 正在解包二进制模型: {os.path.basename(file_path)} ...")
            subprocess.run(["SpineSkeletonDataConverter.exe", file_path, json_file_path], check=True)
            with open(json_file_path, "r", encoding="utf-8") as jf:
                return json.load(jf)
        elif os.path.exists("skel2json.exe"):
            subprocess.run(["skel2json.exe", file_path, json_file_path], check=True)
            with open(json_file_path, "r", encoding="utf-8") as jf:
                return json.load(jf)
        else:
            raise FileNotFoundError("未在当前目录下找到 SpineSkeletonDataConverter.exe 或 skel2json.exe！")

def preprocess_target_layer_json(layer_data, offset_y, root_name):
    """对目标图层的顶级骨骼及其动画平移帧执行预处理偏移"""
    if not layer_data or "bones" not in layer_data:
        return

    bones = layer_data["bones"]
    has_root = any(b.get("name") == root_name for b in bones)

    top_bone_names = set()
    for b in bones:
        b_name = b.get("name")
        b_parent = b.get("parent")
        
        if b_name == root_name:
            top_bone_names.add(b_name)
        elif not b_parent or b_parent == root_name:
            if not has_root or b_parent is None or b_parent == root_name:
                top_bone_names.add(b_name)

    print(f"  📐 [预处理] 成功将以下顶层骨骼 Y 坐标平移 {offset_y}:")
    for b in bones:
        if b.get("name") in top_bone_names:
            old_y = b.get("y", 0)
            b["y"] = old_y + offset_y
            print(f"     └─ 骨骼 [{b.get('name')}]: {old_y} -> {b['y']}")

    if "animations" in layer_data:
        for anim_name, anim_body in layer_data["animations"].items():
            if "bones" in anim_body:
                for b_name, b_anim in anim_body["bones"].items():
                    if b_name in top_bone_names and "translate" in b_anim:
                        for kf in b_anim["translate"]:
                            kf["y"] = kf.get("y", 0) + offset_y

def remap_mesh_vertices(vertices, uvs_len, bone_offset):
    """重映射带权网格的骨骼索引"""
    if not vertices or bone_offset == 0:
        return vertices
    
    if uvs_len and len(vertices) == uvs_len:
        return vertices
        
    new_vertices = list(vertices)
    i = 0
    while i < len(new_vertices):
        try:
            bone_count = int(new_vertices[i])
            i += 1
            for _ in range(bone_count):
                new_vertices[i] = int(new_vertices[i]) + bone_offset
                i += 4
        except (IndexError, ValueError):
            break
            
    return new_vertices

def merge_spine_custom_layers():
    pattern = re.compile(MODEL_CONFIG["FILE_PATTERN"], re.IGNORECASE)
    root_bone_name = MODEL_CONFIG["ROOT_BONE_NAME"]
    
    found_files = []
    for f in os.listdir('.'):
        if f.startswith('combined_model'):
            continue
        match = pattern.match(f)
        if match:
            suffix = match.group(1).lower()
            if suffix in [x.lower() for x in MODEL_CONFIG["IGNORE_LAYERS"]]:
                print(f"🙈 [已跳过] 忽略特定图层文件: {f}")
                continue
            found_files.append((suffix, f))
            
    if not found_files:
        print(f"❌ 未在当前目录下找到符合正则 '{MODEL_CONFIG['FILE_PATTERN']}' 的模型文件！")
        return

    layer_priority = MODEL_CONFIG["LAYER_PRIORITY"]
    found_files.sort(key=lambda item: layer_priority.get(item[0], 99))
    
    print("\n" + "="*60)
    print(f"📦 [参与融合的图层 (由下至上)]: {[x[0] for x in found_files]}")
    print("="*60 + "\n")

    main_data = {
        "skeleton": {"hash": "combined", "spine": "3.8.99", "width": 0, "height": 0},
        "bones": [{"name": root_bone_name}],
        "slots": [],
        "skins": [],
        "animations": {}
    }
    combined_atlas_content = ""
    layer_slots_map = {}        # 记录各个图层包含的插槽名称
    slot_default_attach_map = {} # 记录各插槽的默认附件名（用于生成显示动作）

    for suffix, part_file in found_files:
        prefix = f"{suffix}-"
        is_target_offset_layer = (suffix == MODEL_CONFIG["OFFSET_LAYER_NAME"].lower())
        layer_slots_map[suffix] = []
        
        print(f"🔄 正在读取并处理图层 [{suffix}] -> {part_file} ...")
        
        try:
            part_data = load_skel_file(part_file)
        except Exception as e:
            print(f"⚠️ 读取部件 {part_file} 失败，跳过。错误: {e}")
            continue

        if is_target_offset_layer:
            preprocess_target_layer_json(part_data, MODEL_CONFIG["OFFSET_Y_VALUE"], root_bone_name)

        if "skeleton" in part_data:
            main_data["skeleton"]["spine"] = part_data["skeleton"].get("spine", main_data["skeleton"]["spine"])
            main_data["skeleton"]["width"] = max(main_data["skeleton"].get("width", 0), part_data["skeleton"].get("width", 0))
            main_data["skeleton"]["height"] = max(main_data["skeleton"].get("height", 0), part_data["skeleton"].get("height", 0))

        bone_offset = len(main_data["bones"])

        # A. 合并骨骼
        for bone in part_data.get("bones", []):
            old_name = bone["name"]
            old_parent = bone.get("parent")
            
            new_bone = bone.copy()
            new_bone["name"] = prefix + old_name
            
            if old_name == root_bone_name or not old_parent or old_parent == root_bone_name:
                new_bone["parent"] = root_bone_name
            else:
                new_bone["parent"] = prefix + old_parent
                
            main_data["bones"].append(new_bone)

        # B. 无损合并插槽并记录该图层的插槽与默认附件
        for slot in part_data.get("slots", []):
            new_slot_name = prefix + slot["name"]
            new_slot = slot.copy()
            new_slot["name"] = new_slot_name
            new_slot["bone"] = prefix + slot["bone"]
            
            if new_slot.get("attachment"):
                new_slot["attachment"] = prefix + new_slot["attachment"]
                slot_default_attach_map[new_slot_name] = new_slot["attachment"]
            else:
                slot_default_attach_map[new_slot_name] = None

            main_data["slots"].append(new_slot)
            layer_slots_map[suffix].append(new_slot_name)

        # C. 无损合并 Skins (100% 保留所有表情皮肤)
        skins_list = part_data.get("skins", [])
        if isinstance(skins_list, dict):
            skins_list = [{"name": k, "attachments": v} for k, v in skins_list.items()]

        for part_skin in skins_list:
            skin_name = part_skin.get("name", "default")
            main_skin = next((s for s in main_data["skins"] if s.get("name") == skin_name), None)
            if not main_skin:
                main_skin = {"name": skin_name, "attachments": {}}
                main_data["skins"].append(main_skin)
            
            for slot_name, attach_map in part_skin.get("attachments", {}).items():
                new_slot_name = prefix + slot_name
                new_attach_map = main_skin["attachments"].setdefault(new_slot_name, {})

                for attach_name, attach_data in attach_map.items():
                    new_attach_name = prefix + attach_name
                    new_data = attach_data.copy()
                    if "name" in new_data: 
                        new_data["name"] = prefix + new_data["name"]
                    if "path" in new_data: 
                        new_data["path"] = prefix + new_data["path"]
                    if "vertices" in new_data:
                        uvs_len = len(new_data.get("uvs", []))
                        new_data["vertices"] = remap_mesh_vertices(new_data["vertices"], uvs_len, bone_offset)
                    new_attach_map[new_attach_name] = new_data
                    
                    # 补全可能未在 slots 中指明的默认附件名
                    if slot_default_attach_map.get(new_slot_name) is None:
                        slot_default_attach_map[new_slot_name] = new_attach_name

        # D. 无损合并动画轨 (100% 保留原始动画关键帧)
        if "animations" in part_data:
            for anim_name, anim_content in part_data["animations"].items():
                target_anim = main_data["animations"].setdefault(anim_name, {})
                
                for key, val in anim_content.items():
                    if key == "bones":
                        target_bones = target_anim.setdefault("bones", {})
                        for bk, bv in val.items():
                            target_bones[prefix + bk] = bv

                    elif key == "slots":
                        target_slots = target_anim.setdefault("slots", {})
                        for sk, sv in val.items():
                            patched_sv = {}
                            for tk, keyframes in sv.items():
                                if tk == "attachment":
                                    patched_kf = []
                                    for kf in keyframes:
                                        nkf = kf.copy()
                                        if nkf.get("name"):
                                            nkf["name"] = prefix + nkf["name"]
                                        patched_kf.append(nkf)
                                    patched_sv[tk] = patched_kf
                                else:
                                    patched_sv[tk] = keyframes
                            target_slots[prefix + sk] = patched_sv

                    elif key in ("deform", "attachments"):
                        target_deform = target_anim.setdefault(key, {})
                        for skin_k, skin_v in val.items():
                            target_skin = target_deform.setdefault(skin_k, {})
                            for slot_k, slot_v in skin_v.items():
                                target_slot = target_skin.setdefault(prefix + slot_k, {})
                                for attach_k, attach_v in slot_v.items():
                                    target_slot[prefix + attach_k] = attach_v

                    elif key in ("ik", "transform", "path"):
                        target_category = target_anim.setdefault(key, {})
                        for ck, cv in val.items():
                            target_category[prefix + ck] = cv

                    elif key in ("drawOrder", "draworder"):
                        target_draworder = target_anim.setdefault(key, [])
                        for kf in val:
                            nkf = kf.copy()
                            if "offsets" in nkf:
                                new_offsets = []
                                for off in nkf["offsets"]:
                                    noff = off.copy()
                                    if "slot" in noff:
                                        noff["slot"] = prefix + noff["slot"]
                                    new_offsets.append(noff)
                                nkf["offsets"] = new_offsets
                            target_draworder.append(nkf)
                    else:
                        if isinstance(val, dict):
                            target_dict = target_anim.setdefault(key, {})
                            for sub_k, sub_v in val.items():
                                target_dict[prefix + sub_k] = sub_v
                        elif isinstance(val, list):
                            target_list = target_anim.setdefault(key, [])
                            target_list.extend(val)

        # E. 合并约束
        if "ik" in part_data:
            main_ik = main_data.setdefault("ik", [])
            for ik_item in part_data["ik"]:
                new_ik = ik_item.copy()
                new_ik["name"] = prefix + new_ik["name"]
                if "bones" in new_ik:
                    new_ik["bones"] = [prefix + b for b in new_ik["bones"]]
                if "target" in new_ik:
                    new_ik["target"] = prefix + new_ik["target"]
                main_ik.append(new_ik)

        if "transform" in part_data:
            main_trans = main_data.setdefault("transform", [])
            for tr_item in part_data["transform"]:
                new_tr = tr_item.copy()
                new_tr["name"] = prefix + new_tr["name"]
                if "bones" in new_tr:
                    new_tr["bones"] = [prefix + b for b in new_tr["bones"]]
                if "target" in new_tr:
                    new_tr["target"] = prefix + new_tr["target"]
                main_trans.append(new_tr)

        # F. 合并 Atlas 图集
        part_name = os.path.splitext(part_file)[0]
        part_atlas = part_name + ".atlas"
        if os.path.exists(part_atlas):
            with open(part_atlas, "r", encoding="utf-8") as f:
                atlas_lines = f.readlines()
            cleaned_lines = []
            for i, line in enumerate(atlas_lines):
                stripped = line.strip()
                if not stripped or ':' in stripped or stripped.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    cleaned_lines.append(line)
                else:
                    is_real_page = False
                    for j in range(i + 1, len(atlas_lines)):
                        next_s = atlas_lines[j].strip()
                        if next_s:
                            if next_s.startswith(('size:', 'format:', 'filter:', 'repeat:')):
                                is_real_page = True
                            break
                    if is_real_page:
                        cleaned_lines.append(line)
                    else:
                        indent = line[:-len(line.lstrip())]
                        cleaned_lines.append(f"{indent}{prefix}{stripped}\n")
            combined_atlas_content += "\n" + "".join(cleaned_lines) + "\n"

    # G. 自动生成开关动作 (支持独立开关与多图层组合开关)
    print("\n🎬 正在生成图层的开关动作 (Show/Hide)...")
    exclude_switches = [x.lower() for x in MODEL_CONFIG.get("EXCLUDE_SWITCH_LAYERS", ["m1"])]
    combined_groups = MODEL_CONFIG.get("COMBINED_SWITCH_GROUPS", [])
    processed_in_groups = set()

    # 1. 处理组合开关 (例如将 f 和 b 合并为一个开关动作)
    for grp in combined_groups:
        valid_suffixes = [s.lower() for s in grp if s.lower() in layer_slots_map and s.lower() not in exclude_switches]
        if not valid_suffixes:
            continue
        
        group_name = "_".join(valid_suffixes)
        hide_anim_name = f"hide_layer_{group_name}"
        show_anim_name = f"show_layer_{group_name}"

        hide_slots = main_data["animations"].setdefault(hide_anim_name, {}).setdefault("slots", {})
        show_slots = main_data["animations"].setdefault(show_anim_name, {}).setdefault("slots", {})

        total_slots_count = 0
        for suffix in valid_suffixes:
            processed_in_groups.add(suffix)
            slot_names = layer_slots_map[suffix]
            total_slots_count += len(slot_names)
            for slot_name in slot_names:
                hide_slots[slot_name] = {
                    "attachment": [{"time": 0, "name": None}]
                }
                default_attach = slot_default_attach_map.get(slot_name)
                show_slots[slot_name] = {
                    "attachment": [{"time": 0, "name": default_attach}]
                }

        print(f"  └─ 已生成组合开关动作 [{show_anim_name}] & [{hide_anim_name}] (包含图层 {valid_suffixes}，共 {total_slots_count} 个插槽)")

    # 2. 处理剩余的单图层开关
    for suffix, slot_names in layer_slots_map.items():
        if not slot_names:
            continue
        
        if suffix.lower() in exclude_switches:
            print(f"  🙈 [已跳过开关] 图层 [{suffix}] 设为不生成开关动作")
            continue

        if suffix.lower() in processed_in_groups:
            continue

        hide_anim_name = f"hide_layer_{suffix}"
        show_anim_name = f"show_layer_{suffix}"

        hide_slots = main_data["animations"].setdefault(hide_anim_name, {}).setdefault("slots", {})
        show_slots = main_data["animations"].setdefault(show_anim_name, {}).setdefault("slots", {})

        for slot_name in slot_names:
            hide_slots[slot_name] = {
                "attachment": [{"time": 0, "name": None}]
            }
            default_attach = slot_default_attach_map.get(slot_name)
            show_slots[slot_name] = {
                "attachment": [{"time": 0, "name": default_attach}]
            }

        print(f"  └─ 已生成独立开关动作 [{show_anim_name}] & [{hide_anim_name}] ({len(slot_names)} 个插槽)")

    # H. 修复武器隐藏动作 (如 weapon_0) 误将手部插槽隐藏的问题
    weapon_hide_anims = [a.lower() for a in MODEL_CONFIG.get("WEAPON_HIDE_ANIM_NAMES", ["weapon_0"])]
    hand_keywords = [k.lower() for k in MODEL_CONFIG.get("HAND_SLOT_KEYWORDS", ["hand", "finger"])]

    if weapon_hide_anims and hand_keywords:
        print("\n🔧 正在检查并修复武器动作误隐藏手部插槽的问题...")
        for anim_name, anim_data in main_data.get("animations", {}).items():
            if any(wa in anim_name.lower() for wa in weapon_hide_anims):
                if "slots" in anim_data:
                    slots_to_remove = []
                    for slot_name in anim_data["slots"].keys():
                        if any(hk in slot_name.lower() for hk in hand_keywords):
                            slots_to_remove.append(slot_name)
                    
                    for slot_name in slots_to_remove:
                        del anim_data["slots"][slot_name]
                        print(f"  └─ 已成功修复 [{anim_name}]：解除对手部插槽 [{slot_name}] 的误隐藏！")

    # 输出导出
    output_json = "combined_model.json"
    output_atlas = "combined_model.atlas"
    output_skel = "combined_model.skel"
    
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(main_data, f, indent=4, ensure_ascii=False)

    with open(output_atlas, "w", encoding="utf-8") as f:
        f.write(combined_atlas_content)

    print("\n" + "="*60)
    print("🎉 [合并完成]！已成功包含组合开关与手部误隐修复：")
    print(f"1️⃣ JSON 配置文件: {output_json}")
    print(f"2️⃣ 图集配置文件: {output_atlas}")

    if os.path.exists("SpineSkeletonDataConverter.exe"):
        print("🔄 正在转码导出二进制文件 [combined_model.skel] ...")
        try:
            subprocess.run(["SpineSkeletonDataConverter.exe", output_json, output_skel], check=True)
            print(f"3️⃣ 二进制模型文件: {output_skel}")
        except Exception as e:
            print(f"⚠️ 转码二进制文件失败: {e}")
            
    print("="*60)

if __name__ == '__main__':
    merge_spine_custom_layers()