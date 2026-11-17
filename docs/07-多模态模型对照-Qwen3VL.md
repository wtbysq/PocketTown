# 多模态模型对照：1B vs Qwen3-VL-2B / 4B

> 2026-11-16 · 同机同用例 · llama.cpp（mtmd）· 纯 CPU（`-ngl 0`）· `-c 4096` · 单次采样

---

## 一、为什么测

1B 在 `docs/02` 里栽了三道题（算术、小票总额、路牌禁停）。用户问「还有没有别的多模态模型」，
候选里最现实的是 **Qwen3-VL-2B / 4B**：体积只到手机能承受的量级，中文与 OCR 都比 1B 强一档。

先确认了一件事：**现有运行时就能跑它们，不用重编原生库**。

```
project/app-ocl/libmtmd.so   → qwen3vl ✓ qwen2vl ✓ internvl ✓ minicpmv ✓
project/app-ocl/libllama.so  → qwen3vl ✓ qwen2vl ✓ qwen35moe ✓
testbed/runtime/mtmd.dll     → qwen3vl ✓ qwen2vl ✓ minicpmv ✓ gemma3 ✓ internvl ✓
```

## 二、被测模型

| 代号 | 权重 | 视觉模块 | 下载体积 |
|---|---|---|---|
| `1b`（现状） | MiniCPM-V 4.7 1B Q4_K_M | mmproj-4.7-patched（16×） | 0.64 + 1.06 GB |
| `q2b` | Qwen3-VL-2B-Instruct Q4_K_M | mmproj-F16 | 1.03 + 0.76 GB |
| `q4b` | Qwen3-VL-4B-Instruct Q4_K_M | mmproj-F16 | 2.33 + 0.78 GB |

模型放在 `testbed/models/qwen3-vl-{2b,4b}/`（不进库），下载走 `hf-mirror.com` + `project/tools/pget.py`。

## 三、结果

### 3.1 质量（同一批用例，逐条人工判）

| 用例 | 1B | Qwen3-VL-2B | Qwen3-VL-4B |
|---|---|---|---|
| 算术 `3−2+5` | ⭕ 先答「4 个」再自我纠正到 6，绕了 3 行 | ✅ 直接 `3-2+5=6` | ✅ 直接 `3-2+5=6` |
| 小票总额 | ❌ 答 **212.86**（漏减 15 元会员折扣） | ✅ **197.86**，商品也列对 | ✅ **197.86**，并主动拆出 212.86 −15.00 |
| 柱状图求和（真值 **402**） | ❌ 462 | ❌ 350（直接跳过了加减） | ✅ **402**，且列出算式 `128+96+74+61+43` |
| 路牌禁停 | ❌ 说「14:00 开走」，回来「能停到 21:00」 | ❌ 说「最晚 15:40 开走」，把办事结束时间当成开走时间 | ⭕ 说「14:00 才能合法停车、最晚 16:00 开走」，没说 11:20 正处在禁停时段 |
| 截图 OCR | 读出大部分，SSH 公钥串念错更多（`ed2519`） | 同样念错公钥串 | 同样念错公钥串 |

**3 道可判定的题：1B 对 1、2B 对 2、4B 对 3。**

OCR 三个都不理想——这跟压缩后的图只有 32 KB、图像 token 少有关，手机上按 1024 px 重编应该更好，
不能拿这一条给 Qwen 判死刑。

### 3.2 性能（同一台机器：Ryzen 7 7735H / 8 线程 / 纯 CPU）

| 指标 | 1B | Qwen3-VL-2B | Qwen3-VL-4B |
|---|---|---|---|
| 加载到 `/health` 就绪 | 12.7 s | 6.2 s | 5.6 s |
| 空闲 RSS | 1949 MB | 3002 MB | **5510 MB** |
| 峰值 RSS（实测最高） | 2343 MB | 3914 MB | **6195 MB** |
| 解码速度 | 25–26 tok/s | 16–24 tok/s | **6.3–10.3 tok/s** |
| 小票整题耗时 | 20.3 s | 34.6 s | **62.0 s** |
| 图片预填 | 15.6 s | 31.6 s | 44.4 s |

加载时间的差异不要当真：三个进程都吃页缓存，越大反而越快，只有第一次冷加载才有意义。

## 四、结论

1. **2B 是最合理的一档**：质量上把小票从错到对，内存峰值 3.9 GB（12 GB 机上留得住），
   速度掉到 1B 的六成左右。适合作为「中档」和 1B 并存。
2. **4B 是「答得对」那一档**：三道题全对（含求和），代价是峰值 6.2 GB、解码 6–10 tok/s、
   一张小票 62 秒。11–12 GB 的机器能跑，但会很挤；8 GB 机不要碰。
3. **1B 仍然是最快的一档**，纯文字对话优势明显（25 tok/s），但读数类任务不要指望它。
4. **三档并存是可行的产品形态**：1B 保底 / 2B 推荐 / 35B-A3B 旗舰，跟 `docs/01` 的双档设计同源，只是多一档。

## 五、要落进 App 还需要做什么

> 下表前四项已在 2026-11-16 落地（真机验证见第六节）；提示词重调与模型包分发仍未做。

| 事项 | 说明 |
|---|---|
| 模型档案 | `MainActivity` 现在只有 `1b` / `35b` 两档（`ID_1B` / `ID_35B`、`modelDir()`、`modelFile()`）。加 2B/4B 要新增 id、目录、文件名与切换逻辑 |
| 内存门槛 | 现在是 `ram >= 15 GB` 才允许 35B。用实测反推：2B 峰值 3.9 GB → 门槛约 6 GB；4B 峰值 6.2 GB → 门槛约 9 GB（手机侧还要重测，PC 与手机不一致） |
| 看图内存保护 | `index.html` 的 2.3 / 2.8 / 3.2 GB 三档是按 1B 实测的，换模型必须重跑 `vision-load-test.py` |
| 身份兜底 | `fixSelfName` 里写死「MiniCPM / 面壁 / OpenBMB」，Qwen 会说「我是通义千问」，要一起改 |
| 提示词 | `systemPrompt` 的四条硬规则 + 示例是针对 1B 调的；4B 更听话，但也更容易啰嗦，需要重调 |
| 模型包分发 | 15 GB 的 35B 已经够呛，再加 3.1 GB 的 4B，下载器必须支持断点续传（现在只支持「导入 zip」） |

## 六、真机实测（红米 K60 Pro · 2026-11-16）

设备：Android 16 / 11.2 GB RAM（MemTotal 10.9 GB）/ arm64，adb + WebView CDP 驱动。

| 项 | 1B（现状） | Qwen3-VL-2B（新装） | Qwen3-VL-4B（新装） |
|---|---|---|---|
| 引擎 RSS | 929 MB（峰值 1094 MB） | 2409 MB（峰值 2458 MB） | 3798 MB（峰值 3819 MB） |
| 解码 | 30–39 tok/s | 21–31 tok/s | **6.4 tok/s** |
| 小票整题 | 43.8 s（答 212.86，错） | 看图崩溃 | 未测（看图同崩） |
| 文本算术 | 先答 4 再改口 6 | 6（直连 API）／8（走 App 完整人设，首字 17 s） | 6（直连 API，总计 7.4 s） |
| 图片 | 正常（GPU 视觉） | **SIGSEGV** | **未测，预期同样崩** |

**崩溃证据**（`adb logcat -b crash`）：

```
signal 11 (SIGSEGV), code 1 (SEGV_MAPERR), fault addr 0x0
#00 libggml-base.so  ggml_gallocr_alloc_graph+1576
#01 libggml-base.so  ggml_backend_sched_alloc_graph+464
#02 libmtmd.so       clip_encode+564
#03 libmtmd.so       clip_image_batch_encode+84
#05 libmtmd.so       mtmd_batch_encode+1292
```

去掉 `--mmproj-offload`（纯 CPU 视觉）后同样崩在同一处，说明**不是 GPU 后端的问题**，
而是当前 `libmtmd.so` 对 Qwen3-VL 视觉塔（动态分辨率 + deepstack）支持不完整——
引擎 warmup 阶段本来就在喊：

```
warmup: flash attention is disabled
warmup: please report this on github as an issue
warmup: ref: https://github.com/ggml-org/llama.cpp/pull/16837#issuecomment-3461676118
```

### 已落进 App 的部分

- 模型档案扩成 4 档：`1b / 2b / 4b / 35b`（目录 `models` / `models2b` / `models4b` / `models35`）
- 内存门槛：2B ≥ 6 GB、4B ≥ 9 GB、35B ≥ 15 GB（按 PC 峰值 +2 GB 系统余量）
- 模型页新增「对话模型」卡片：三档按钮 + 已导入状态 + 内存不足置灰
- 切换走 `setModel()` → 重启引擎 → 页面轮询 `/health` 后刷新
- Qwen 档启动带 `--jinja`（思考开关在它自己的模板里），视觉强制走 CPU（GPU 路径已验证会崩）
- **看图入口对 Qwen 档直接拦掉**：点「照片」提示"这版只能文字，看图请切回 1B"，
  避免用户点一次图就把引擎弄崩
- `fixSelfName` 补上 `通义千问 / Qwen / 阿里`，否则被问"你不就是通义千问吗"会顺着演

## 七、结论修正

原结论「2B 可以当中档」需要收窄：**在现有运行时里，2B/4B 只能做文字档**，看图仍只有 1B。
要让它看图，只有两条路：

1. **重编 `libmtmd.so` / `libllama.so`**（上游新版本对 qwen3vl 支持更完整）。
   当前工作区没有 llama.cpp 源码目录，需要重新拉源码 + NDK r28b 交叉编译，工作量以半天到一天计。
2. **换 Qwen2.5-VL-3B**（`qwen2vl` 架构这个库是支持的，1B 之外唯一"已验证能看图"的家族），
   代价是再下 ~2.4 GB 并重测。

## 八、这次测的局限

- **单次采样**：1B 的答案本身就不稳（同一提示词两次能给相反答案，见 `docs/05`）。要下定论，每题至少跑 3 轮。
- **PC 不是手机**：绝对数字不能搬到红米 K60 Pro 上；相对排序（1B 快 / 4B 准）可信。
- **图太小**：样本图 32–84 KB，手机端会按 1024 px 重新编码，视觉 token 更多，OCR 结果可能更好、也更慢。
- **没测 8192 上下文**：为了省内存用的 `-c 4096`；App 默认 8192 + KV q8，内存会再高一些。

## 七、复现

```bash
# 下载（hf-mirror）
python project/tools/pget.py https://hf-mirror.com/unsloth/Qwen3-VL-2B-Instruct-GGUF/resolve/main/Qwen3-VL-2B-Instruct-Q4_K_M.gguf \
  testbed/models/qwen3-vl-2b/Qwen3-VL-2B-Instruct-Q4_K_M.gguf 16
python project/tools/pget.py https://hf-mirror.com/unsloth/Qwen3-VL-2B-Instruct-GGUF/resolve/main/mmproj-F16.gguf \
  testbed/models/qwen3-vl-2b/mmproj-F16.gguf 16

# 对照（每档一条命令；脚本自己起引擎、跑用例、记 RSS、收尾退出）
python testbed/bakeoff.py --name q2b \
  --model models/qwen3-vl-2b/Qwen3-VL-2B-Instruct-Q4_K_M.gguf \
  --mmproj models/qwen3-vl-2b/mmproj-F16.gguf --port 8092
```

明细：`testbed/logs/bakeoff-{1b,q2b,q4b}.json`，引擎日志 `bakeoff-*-server.log`。
