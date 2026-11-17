#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""按档生成可导入的模型包（PocketTown-<模型名>-<版本>.zip）。

三档分开打，谁要哪档就下哪个，不再出一个 6 GB 的整包；
文件名直接带模型名，下载页里不用再点进去看是哪个模型：

    PocketTown-MiniCPM-V-4.7-1B-2.1.0.zip   1B（含视觉投影器）
    PocketTown-Qwen3-VL-2B-2.1.0.zip        2B（含投影器）
    PocketTown-Qwen3-VL-4B-2.1.0.zip        4B（含投影器）

语音（识别 + 6 个音色）已经打进 APK，模型包里不带。
zip 第一个条目固定是 manifest.json（每个文件的相对路径与字节数），
App 用它做空间预估和完整性校验；manifest 里额外的 model / label 字段
只是给人看的，App 不依赖。

用法：
    python app/make-model-zip.py                  # 三档都打
    python app/make-model-zip.py --only 2b        # 只打一档
    python app/make-model-zip.py --only 1b,4b --ver 2.1.0
    python app/make-model-zip.py --models-dir D:/models --out-dir D:/dist
"""
import argparse
import json
import os
import sys
import time
import zipfile

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP_DIR)                      # project/
WORKSPACE = os.path.dirname(ROOT)                    # 工作区根目录

BRAND = "PocketTown"

# 每档：(档位 id, 显示名, 文件名用的短名, [(磁盘相对路径, zip 内路径)])
GROUPS = {
    "1b": ("MiniCPM-V 4.7 · 1B", "MiniCPM-V-4.7-1B", [
        ("MiniCPM-V-4_7-1B-Q4_K_M.gguf", "models/MiniCPM-V-4_7-1B-Q4_K_M.gguf"),
        ("mmproj-4.7-patched.gguf", "models/mmproj-4.7-patched.gguf"),
    ]),
    "2b": ("Qwen3-VL · 2B", "Qwen3-VL-2B", [
        ("qwen3-vl-2b/Qwen3-VL-2B-Instruct-Q4_K_M.gguf",
         "models2b/Qwen3-VL-2B-Instruct-Q4_K_M.gguf"),
        ("qwen3-vl-2b/mmproj-F16.gguf", "models2b/mmproj-F16.gguf"),
    ]),
    "4b": ("Qwen3-VL · 4B", "Qwen3-VL-4B", [
        ("qwen3-vl-4b/Qwen3-VL-4B-Instruct-Q4_K_M.gguf",
         "models4b/Qwen3-VL-4B-Instruct-Q4_K_M.gguf"),
        ("qwen3-vl-4b/mmproj-F16.gguf", "models4b/mmproj-F16.gguf"),
    ]),
}

CHUNK = 4 * 1024 * 1024


def default_models_dir():
    for p in (os.path.join(WORKSPACE, "testbed", "models"),
              os.path.join(WORKSPACE, "models"),
              os.path.join(ROOT, "models")):
        if os.path.isdir(p):
            return p
    return os.path.join(WORKSPACE, "testbed", "models")


def add_stream(zf, arcname, path, compress):
    size = os.path.getsize(path)
    info = zipfile.ZipInfo(arcname)
    info.compress_type = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    info.external_attr = (0o644 & 0xFFFF) << 16
    info.file_size = size
    # 单个条目超过 2 GB（4B 主模型 2.5 GB）必须走 ZIP64；Android 的 ZipInputStream
    # 和桌面解压工具都认，App 导入也是顺序读，不依赖中央目录。
    with open(path, "rb") as src, zf.open(info, "w", force_zip64=size > 0x7FFFFFFF) as dst:
        left = size
        while left > 0:
            chunk = src.read(min(CHUNK, left))
            if not chunk:
                break
            dst.write(chunk)
            left -= len(chunk)


def packed_size(files):
    return sum(os.path.getsize(p) for p, _ in files)


def build_one(mid, label, slug, files, models_dir, out_dir, ver):
    missing = [src for src, _ in files if not os.path.exists(os.path.join(models_dir, src))]
    if missing:
        print("跳过 %s：缺文件" % mid)
        for m in missing:
            print("   " + m)
        return None

    out = os.path.join(out_dir, "%s-%s-%s.zip" % (BRAND, slug, ver))
    total = packed_size([(os.path.join(models_dir, src), arc) for src, arc in files])
    manifest = {
        "version": ver,
        "brand": BRAND,
        "model": mid,
        "label": label,
        "total": total,
        "files": [{"path": arc, "size": os.path.getsize(os.path.join(models_dir, src))}
                  for src, arc in files],
    }

    t0 = time.time()
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, allowZip64=True,
                         compresslevel=6) as zf:
        # manifest 放第一个，App 一进来就能算空间、知道要解哪些文件
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        for src, arc in files:
            path = os.path.join(models_dir, src)
            print("   %-46s %6.1f MB" % (arc, os.path.getsize(path) / 1048576.0))
            add_stream(zf, arc, path, True)

    size = os.path.getsize(out)
    print(" → %s" % out)
    print("   原始 %.2f GB → 压缩后 %.2f GB（手机要留 %.2f GB 空间），用时 %.0fs\n"
          % (total / 1073741824.0, size / 1073741824.0, total / 1073741824.0,
             time.time() - t0))
    return {"model": mid, "label": label, "file": out, "raw": total, "zip": size}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="1b,2b,4b",
                    help="逗号分隔：1b / 2b / 4b（默认三档都打）")
    ap.add_argument("--ver", default=os.environ.get("MODEL_PKG_VER", "2.1.0"))
    ap.add_argument("--models-dir", default=default_models_dir())
    ap.add_argument("--out-dir", default=os.path.join(ROOT, "out"))
    args = ap.parse_args()

    ids = [x.strip().lower() for x in args.only.split(",") if x.strip()]
    unknown = [x for x in ids if x not in GROUPS]
    if unknown:
        sys.exit("不认识的档位：%s（可选 %s）" % (", ".join(unknown), ", ".join(GROUPS)))

    if not os.path.isdir(args.models_dir):
        sys.exit("找不到模型源目录：%s" % args.models_dir)
    os.makedirs(args.out_dir, exist_ok=True)

    print("模型源：%s\n输出：%s\n版本：%s\n" % (args.models_dir, args.out_dir, args.ver))
    done = []
    for mid in ids:
        label, slug, files = GROUPS[mid]
        print("── %s（%s）" % (mid.upper(), label))
        rec = build_one(mid, label, slug, files, args.models_dir, args.out_dir, args.ver)
        if rec:
            done.append(rec)

    if not done:
        sys.exit("没有生成任何模型包")

    print("══ 汇总 ══")
    for r in done:
        print("  %-4s %-40s %6.2f GB（压缩后）" % (r["model"].upper(),
                                                  os.path.basename(r["file"]), r["zip"] / 1073741824.0))
    print("  合计 %.2f GB" % (sum(r["zip"] for r in done) / 1073741824.0))


if __name__ == "__main__":
    main()
