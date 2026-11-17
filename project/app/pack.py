#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 aapt2 产出的资源包 + dex + assets（网页 / 语音 / 音色）+ 原生库 组装成未对齐的 APK。

默认只带语音（ASR + 6 个音色），大模型走单独的模型包导入；BUNDLE_MODELS=1 时才把
1B 文本模型 + 视觉投影器分片塞进 assets/models/（品牌整合包用）。
分片是为了避开单 asset 超过 1GB 的读取问题，App 首次启动按编号拼接还原。
"""
import os
import struct
import sys
import zipfile

ROOT = "D:/kcpm"
BASE = os.path.join(ROOT, "build", "base.apk")
DEX_DIR = os.path.join(ROOT, "build", "dex")
ASSETS = os.path.join(ROOT, "app", "assets")
LIBS = os.path.join(ROOT, "app-ocl")   # OpenCL 构建产物（视觉编码走 GPU）
LIBS_EXTRA = os.path.join(ROOT, "speech", "libs")   # sherpa-onnx / onnxruntime
MODELS = "D:/口袋CPM/testbed/models"
OUT = os.path.join(ROOT, "build", "unaligned.apk")

# 内置语音模型：(磁盘文件, APK 内路径)。
# 识别 1 套 + 朗读 6 个音色（female/male/bronya/theresa/zzl/doom），全部随包，
# App 里按需解出——只有实际用到的音色才写盘，见 MainActivity.prepareVoice。
SPEECH_FILES = [
    ("D:/kcpm/speech/asr/model.int8.onnx", "speech/asr/model.int8.onnx"),
    ("D:/kcpm/speech/asr/tokens.txt", "speech/asr/tokens.txt"),
    # 女声
    ("D:/kcpm/speech/tts-fc/vits-zh-hf-fanchen-C/vits-zh-hf-fanchen-C.onnx", "speech/tts/model.onnx"),
    ("D:/kcpm/speech/tts-fc/vits-zh-hf-fanchen-C/tokens.txt", "speech/tts/tokens.txt"),
    ("D:/kcpm/speech/tts-fc/vits-zh-hf-fanchen-C/lexicon.txt", "speech/tts/lexicon.txt"),
    ("D:/kcpm/speech/tts-fc/vits-zh-hf-fanchen-C/date.fst", "speech/tts/date.fst"),
    ("D:/kcpm/speech/tts-fc/vits-zh-hf-fanchen-C/number.fst", "speech/tts/number.fst"),
    ("D:/kcpm/speech/tts-fc/vits-zh-hf-fanchen-C/phone.fst", "speech/tts/phone.fst"),
    ("D:/kcpm/speech/tts-fc/vits-zh-hf-fanchen-C/new_heteronym.fst",
     "speech/tts/new_heteronym.fst"),
    # 男声
    ("D:/kcpm/speech/tts-m/vits-zh-hf-fanchen-wnj.onnx", "speech/tts_m/model.onnx"),
    ("D:/kcpm/speech/tts-m/tokens.txt", "speech/tts_m/tokens.txt"),
    ("D:/kcpm/speech/tts-m/lexicon.txt", "speech/tts_m/lexicon.txt"),
    ("D:/kcpm/speech/tts-m/date.fst", "speech/tts_m/date.fst"),
    ("D:/kcpm/speech/tts-m/number.fst", "speech/tts_m/number.fst"),
    ("D:/kcpm/speech/tts-m/phone.fst", "speech/tts_m/phone.fst"),
    ("D:/kcpm/speech/tts-m/new_heteronym.fst", "speech/tts_m/new_heteronym.fst"),
]

# 另外 4 个音色：speech/voices/tts_<key>/ 下已经是 model.onnx 这种标准命名
for _v in ("bronya", "theresa", "zzl", "doom"):
    _src = "D:/kcpm/speech/voices/tts_" + _v
    for _n in ("model.onnx", "tokens.txt", "lexicon.txt",
               "date.fst", "number.fst", "phone.fst", "new_heteronym.fst"):
        SPEECH_FILES.append((os.path.join(_src, _n), "speech/tts_%s/%s" % (_v, _n)))

# 内置进 APK 的模型：文本主模型 + 视觉投影器（全量版）
BUNDLED_MODELS = [
    "MiniCPM-V-4_7-1B-Q4_K_M.gguf",
    "mmproj-4.7-patched.gguf",
]

SKIP = {"libllama-cli-impl.so", "llama-cli"}
CHUNK = 4 * 1024 * 1024
PART_SIZE = 400 * 1024 * 1024  # 每片 400MB，远低于单 asset 1GB 的隐患线
# 默认不带大模型（走模型包导入）；BUNDLE_MODELS=1 出把 1B 也塞进去的整合包。
# 语音（ASR + 6 个音色）永远打包，不随这个开关走。
BUNDLE_MODELS = os.environ.get("BUNDLE_MODELS", "0") != "0"


def add(zf, arcname, path):
    with open(path, "rb") as f:
        data = f.read()
    info = zipfile.ZipInfo(arcname)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (0o644 & 0xFFFF) << 16
    zf.writestr(info, data)


ALIGN = 4
PAD_ID = 0xD935   # 业界惯例的对齐填充字段 ID（zipalign 用的也是这个）


def pad_for(zf, arcname):
    """算出让数据段落在 4 字节边界所需的 extra 字段（等价 zipalign）。

    包里超过 2GB 时 zipalign 直接罢工（32 位偏移），所以在组包阶段就把
    STORED 条目的数据段自己对齐。
    """
    pos = zf.fp.tell()
    base = pos + 30 + len(arcname.encode("utf-8"))
    pad = (-base) % ALIGN
    if pad == 0:
        return b""
    if pad < 4:
        pad += 4
    return struct.pack("<HH", PAD_ID, pad - 4) + b"\x00" * (pad - 4)


def add_stored(zf, arcname, path, offset=0, length=None):
    """大文件不压缩、流式写入，可只取其中一段。"""
    size = os.path.getsize(path)
    if length is None:
        length = size - offset
    info = zipfile.ZipInfo(arcname)
    info.compress_type = zipfile.ZIP_STORED
    info.file_size = length
    info.external_attr = (0o644 & 0xFFFF) << 16
    with open(path, "rb") as f, zf.open(info, "w") as dst:
        f.seek(offset)
        left = length
        while left > 0:
            chunk = f.read(min(CHUNK, left))
            if not chunk:
                break
            dst.write(chunk)
            left -= len(chunk)


def add_deflated(zf, arcname, path, offset=0, length=None):
    """流式 deflate 写入（模型能压掉不少，用来把总包压在 2GB 以内）。"""
    if length is None:
        length = os.path.getsize(path) - offset
    info = zipfile.ZipInfo(arcname)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (0o644 & 0xFFFF) << 16
    with open(path, "rb") as f, zf.open(info, "w") as dst:
        f.seek(offset)
        left = length
        while left > 0:
            chunk = f.read(min(CHUNK, left))
            if not chunk:
                break
            dst.write(chunk)
            left -= len(chunk)


def dir_entry(zf, name):
    di = zipfile.ZipInfo(name)
    di.compress_type = zipfile.ZIP_STORED
    di.external_attr = (0o40755 << 16) | 0x10
    zf.writestr(di, b"")


def main():
    if os.path.exists(OUT):
        os.remove(OUT)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for d in ("assets/", "assets/models/", "assets/speech/", "assets/speech/asr/",
                  "assets/speech/tts/", "assets/speech/tts_m/", "lib/", "lib/arm64-v8a/"):
            dir_entry(zf, d)

        # 1) aapt2 产出的资源与清单（resources.arsc 必须保持 STORED）
        with zipfile.ZipFile(BASE) as src:
            for info in src.infolist():
                data = src.read(info.filename)
                ni = zipfile.ZipInfo(info.filename)
                ni.compress_type = info.compress_type
                ni.external_attr = info.external_attr
                zf.writestr(ni, data)

        # 2) classes.dex
        dexes = sorted(f for f in os.listdir(DEX_DIR) if f.endswith(".dex"))
        if not dexes:
            sys.exit("没有找到 dex，d8 可能失败了")
        for d in dexes:
            add(zf, d, os.path.join(DEX_DIR, d))

        # 3) 网页资源
        for name in sorted(os.listdir(ASSETS)):
            p = os.path.join(ASSETS, name)
            if os.path.isfile(p):
                add(zf, "assets/" + name, p)

        # 3b) 子目录里的图片资源（assets/img/*.jpg）
        for sub in ("img",):
            subdir = os.path.join(ASSETS, sub)
            if os.path.isdir(subdir):
                dir_entry(zf, "assets/" + sub + "/")
                for name in sorted(os.listdir(subdir)):
                    p = os.path.join(subdir, name)
                    if os.path.isfile(p):
                        add(zf, "assets/%s/%s" % (sub, name), p)

        # 4) 内置大模型（可选；只有 BUNDLE_MODELS=1 的整合包才塞）
        if BUNDLE_MODELS:
            for name in BUNDLED_MODELS:
                p = os.path.join(MODELS, name)
                if not os.path.exists(p):
                    sys.exit("找不到要打包的模型：%s" % p)
                size = os.path.getsize(p)
                parts = (size + PART_SIZE - 1) // PART_SIZE
                print("   打包模型 %s (%.0f MB, %d 片)" % (name, size / 1048576.0, parts))
                squeeze = name.endswith(".gguf") and "mmproj" in name
                for i in range(parts):
                    off = i * PART_SIZE
                    arc = "assets/models/%s.%03d" % (name, i)
                    length = min(PART_SIZE, size - off)
                    if squeeze:
                        add_deflated(zf, arc, p, off, length)
                    else:
                        add_stored(zf, arc, p, off, length)
        else:
            print("   （不带大模型：1B / 2B / 4B 统一由模型包导入）")

        # 4b) 内置语音（识别 + 6 个音色）：与上面的开关无关，永远进包
        for src, arcbase in SPEECH_FILES:
            if not os.path.exists(src):
                sys.exit("找不到语音模型：%s" % src)
            size = os.path.getsize(src)
            parts = max(1, (size + PART_SIZE - 1) // PART_SIZE)
            print("   打包语音 %s (%.1f MB)" % (os.path.basename(src), size / 1048576.0))
            squeeze = arcbase.endswith(".onnx")
            for i in range(parts):
                off = i * PART_SIZE
                name = "assets/%s.%03d" % (arcbase, i)
                length = min(PART_SIZE, size - off)
                if squeeze:
                    add_deflated(zf, name, src, off, length)
                else:
                    add_stored(zf, name, src, off, length)

        # 5) 原生库（装包后由系统解压到 nativeLibraryDir，可执行）
        for libdir in (LIBS, LIBS_EXTRA):
            if not os.path.isdir(libdir):
                continue
            for name in sorted(os.listdir(libdir)):
                if not name.endswith(".so") or name in SKIP:
                    continue
                add(zf, "lib/arm64-v8a/" + name, os.path.join(libdir, name))

    print("组包完成：%s (%.0f MB)" % (OUT, os.path.getsize(OUT) / 1048576.0))


if __name__ == "__main__":
    main()
