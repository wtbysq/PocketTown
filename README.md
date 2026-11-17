# 口袋小镇（PocketTown）

一台安卓手机上的**完全离线 AI 聊天应用**。会话即联系人：每个 AI 是有名字、头像、人设的独立角色，可以单聊，也可以把多个角色拉进群里聊。模型、语音、数据全部留在本机，除 `127.0.0.1:8080` 外不发起任何网络请求。

- 当前版本：**1.2.0**（versionCode 44，minSdk 28 / targetSdk 34），包名 `com.koudai.town`
- 1.1.0 及以前叫「口袋 CPM」（`com.koudai.cpm`）。改包名等于新应用，旧版的聊天记录不会自动过来，需要先在旧版导出存档再在新版导入
- 模型：MiniCPM-V 4.7 **1B**（Q4_K_M，含视觉投影器，能看图）／ Qwen3-VL **2B**、**4B**（Q4_K_M，只能文字）／ 35B（旗舰机，当前未开放）；三档各自一个 zip，按需导入，1B 为 Apache-2.0
- 语音：SenseVoice 离线识别 + VITS 本地朗读（6 个音色）
- 界面：原生 JS 单文件（`index.html`，约 3300 行），无框架、无构建步骤

## 功能

| 模块 | 说明 |
|---|---|
| 联系人 | 名字（全局唯一）、头像（内置 12 款 + 相册导入）、人设、长期记忆，独立音色与自动朗读 |
| 群聊 | 2–10 人，成员各自保留人设与记忆；点头像 / 长按头像 @ 指定谁回答；一条消息可 @ 多人，按序各答一次 |
| 我 | 底部「我」标签页：名字、签名、城市 / 工作 / 家人 / 喜好 / 雷区。全局一份，所有联系人和群共用，改完立刻生效，不用每个联系人各填一遍 |
| 记忆 | 两档：上面「我」的资料每轮按问答式注入 system；每个联系人另有自己的长期记忆（≤400 字）和记忆卡（≤60 字/条、≤30 条，长按 AI 回复存入）。聊天里说「我叫阿哲」会弹「记住」胶囊，点了写进「我」 |
| 输出 | 默认流式逐字显示；设置里可关掉，改为整段生成完一次性出现（代码块和表格不会边生成边跳），统计里的「首字」相应换成「整段」 |
| 看图 | 支持发图问答，视觉编码走 Adreno GPU（OpenCL），可退回纯 CPU |
| 文档 | 选 `.docx` 读正文（零依赖：ZIP + SAX，新增 `DocxReader`），按段落切 900 字块逐块提问再汇总；只读文字，`.doc`/PDF/加密文档不支持，原文件不会被改动 |
| 模型档 | 1B（MiniCPM-V 4.7，默认档）/ 2B / 4B（Qwen3-VL）/ 35B（旗舰机，未开放）可切换；三档都要导入各自的模型包；Qwen 档在现有运行时**只能文字**，看图会崩，所以图片入口会拦掉（`docs/07` 有 tombstone 证据） |
| 语音 | 麦克风口述转文字；按联系人音色朗读，可自动朗读 |
| 存档 | 一键导出 `Download/口袋小镇/koudai-存档-时间戳.json`，换机可完整恢复 |
| 检索与管理 | 联系人页「联系人 / 群聊」双标签 + 按名字搜索；长按行删除需二次确认 |

## 目录

```
.
├── project/
│   ├── app/                  应用源码与构建脚本
│   │   ├── src/com/koudai/town/  MainActivity · SpeechEngine · EngineHolder · EngineService · DocxReader
│   │   ├── assets/           前端单文件 index.html + 角色形象
│   │   ├── res/              图标资源
│   │   ├── AndroidManifest.xml
│   │   ├── build-apk.sh      六步构建：aapt2 → javac → d8 → 组包 → zipalign → 签名
│   │   ├── pack.py           组装 APK（资源 + dex + assets + 原生库）
│   │   ├── make-model-zip.py 生成模型包
│   │   └── host-tc.cmake / host-toolchain.cmake   宿主编译配置
│   ├── tools/                图片裁切（ImgTool）、音色包打包、模型下载
│   └── out/                  构建产物（不进库）
├── testbed/                  电脑端联调台（不进库）
│   ├── runtime/              llama-server.exe + ggml/mtmd dll
│   ├── models/               MiniCPM-V 4.7 1B + 修过的 mmproj
│   ├── mock-engine.py        零依赖假引擎（静态站点 + SSE），打印收到的 system prompt
│   ├── persona-test.py · ab-facts.py · vision-load-test.py · docx-flow-e2e.py   真引擎测试脚本
│   ├── memory-facts-test.js · me-page-test.js · stream-test.js · docx-flow-test.js   前端单测（node）
│   └── docx-reader-test/     合成 docx 样本 + DocxReader 的桌面单测
└── docs/
    ├── 01-项目计划书.md
    ├── 02-技术验证报告.md
    ├── 03-结构说明.md        架构、数据模型、桥接口、打包、检查清单
    ├── 04-使用说明.md        安装、导入、功能、FAQ
    ├── 05-人设与记忆测试报告.md
    ├── 06-看图内存压测报告.md
    └── 07-多模态模型对照-Qwen3VL.md
```

## 构建

### 依赖

| 组件 | 版本 | 用途 |
|---|---|---|
| JDK | 17 | javac / d8 / apksigner |
| Android SDK build-tools | 34/35 | aapt2、zipalign、apksigner |
| Android NDK | r28b | 重新编译 llama.cpp 原生库时使用 |

仓库**不包含**以下二进制（体积原因），需自行准备：

- `app-ocl/`：llama.cpp b11669 的 arm64 原生库（含 OpenCL），由 NDK 交叉编译产出
- `speech/`：SenseVoice 识别模型、VITS 音色、sherpa-onnx Java API 源码与 `libonnxruntime.so`
- 模型权重：MiniCPM-V 4.7 1B GGUF + mmproj

### 步骤

```bash
cd project
TARGET_SDK=34 OUT_NAME=PocketTown-1.2.0.apk bash app/build-apk.sh
```

产物在 `project/out/`。默认包的策略是**语音进包、大模型外置**：

- APK 约 **830 MB**：代码 + ASR 识别 + 6 个音色（按需解出，只有用到的才写盘）
- 大模型**按档分开打包**，一档一个 zip，要哪档导哪档：

  | 模型包 | 压缩后 | 解压占用 |
  |---|---|---|
  | `PocketTown-MiniCPM-V-4.7-1B-2.1.0.zip` | 1.43 GB | 1.66 GB |
  | `PocketTown-Qwen3-VL-2B-2.1.0.zip` | 1.60 GB | 1.79 GB |
  | `PocketTown-Qwen3-VL-4B-2.1.0.zip` | 2.88 GB | 3.10 GB |

- `BUNDLE_MODELS=1` 才会把 1B 权重再塞进 APK（整合包约 1.9 GB），一般不用

模型包：

```bash
python app/make-model-zip.py              # 三档各出一个 zip
python app/make-model-zip.py --only 2b    # 只打一档
MODEL_PKG_VER=2.1.0 python app/make-model-zip.py   # 指定版本号
```

音色已经在 APK 里，`tools/make-voices-zip.py` 只用于给老版本补音色。

### 路径注意事项

aapt2 / javac 等工具**不支持非 ASCII 路径**。若工程放在中文目录下（例如 `D:\口袋CPM\project`），构建时需先用 ASCII 目录联接作为入口：

```powershell
New-Item -ItemType Junction -Path 'D:\kcpm' -Target 'D:\口袋CPM\project'
```

然后 `cd /d/kcpm` 执行构建（可用环境变量 `KCPM_ROOT` 指定其它根目录，脚本会在缺失时提示）。

## 安装与使用

装完 APK 语音和 6 个音色就能用；对话还需要在「设置 → 模型包 → 导入 .zip」导入模型包。三档是三个独立的包，只导要用的那档即可（1B 约 1.4 GB，够日常用；想试 2B / 4B 再各导一份）。详细步骤见 [docs/04-使用说明.md](docs/04-使用说明.md)。

安装包与模型包体积较大，不放进仓库，随 Release 附带：

- 下载页：<https://github.com/wtbysq/PocketTown/releases>
- 1.2.0：`PocketTown-1.2.0.apk`（830 MB）· 模型包三份：`PocketTown-MiniCPM-V-4.7-1B-2.1.0.zip`（1.4 GB）、`PocketTown-Qwen3-VL-2B-2.1.0.zip`（1.6 GB）、`PocketTown-Qwen3-VL-4B-2.1.0.zip`（2.9 GB）
- GitHub Release 单资产上限 2 GB，4B 包在下载页拆成 `.zip.001` / `.zip.002` 两段，下载后合并再用：

  ```bat
  copy /b PocketTown-Qwen3-VL-4B-2.1.0.zip.001+PocketTown-Qwen3-VL-4B-2.1.0.zip.002 PocketTown-Qwen3-VL-4B-2.1.0.zip
  ```

  合并后应为 3,095,680,357 字节。1B / 2B 不受限制，直接下载即可。
- 1.1.0（旧名）：`koudai-cpm-1.1.0-lite.apk` + `koudai-models-1.0.0.zip` + `koudai-voices-1.0.0.zip`，仍在同一个 Release 页

## 技术要点

- **零网络**：除本机 `127.0.0.1:8080` 的推理进程外不发请求；WebView 只放行 `android_asset` 与本机地址
- **热启动**：引擎由前台服务保活，退出界面不杀进程，重入约 1 秒；通知栏可「结束引擎」立即释放
- **上下文**：8192 tokens，KV cache 用 q8 量化（同内存装两倍上下文），启动失败自动回退 4096
- **群聊身份隔离**：只有当前发言人的话算 `assistant`，其他人的话放在用户侧并带名字，避免多个 AI 串成一个口吻
- **用户资料用问答式注入**：`问：和你聊天的人叫什么？答：阿哲`，而不是「用户叫阿哲」——1B 会把后者读成自己的名字（5 种写法 × 6 次实测，问答式 0 次混淆）
- **看图内存门槛按实测反推**：视觉编码固定吃 1.06~1.32 GB，与图片大小无关，门槛定在 2.3 GB 起
- **无 XSS 面**：Markdown 先转义再处理格式，不生成 `<a>`/`<img>`

## 测试

- **电脑端联调台**（`testbed/`，不进库）：真 `llama-server.exe` + 真模型托管真前端，或 `mock-engine.py` 零依赖假引擎；后者会把收到的 system prompt 全文打出来，改提示词时最直观
- **前端单测**（node，零依赖）：`memory-facts-test.js`（记忆注入 27 项）、`me-page-test.js`（「我」页表单读写 17 项）、`stream-test.js`（流式/非流式解析 13 项）、`docx-flow-test.js`（切块 + DOM/桥接一致性 32 项）
- **docx 解析单测**（桌面 JDK，零 Android 依赖）：`testbed/docx-reader-test/` 生成 6 个合成 docx 跑 24 项，覆盖表格、域代码、非 ZIP、超长截断
- **真机测试**：`persona-test.py`（人设/名字/记忆一致性）、`vision-load-test.py`（看图内存压测，报告见 docs/06）

## 数据与隐私

| 数据 | 位置 |
|---|---|
| 联系人、群聊、聊天记录、设置 | 应用内部存储（WebView localStorage） |
| 模型 / 语音模型 | 应用私有目录，非 root 不可读 |
| 存档 | `/sdcard/Download/口袋小镇/`（可拷走） |

卸载即清空内部数据，请先导出存档。

## 第三方

- [llama.cpp](https://github.com/ggml-org/llama.cpp)（MIT）
- [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)（Apache-2.0）
- MiniCPM-V 4.7 模型（Apache-2.0，版权归 OpenBMB）
- 音色：VITS 中文模型，来自 [csukuangfj](https://huggingface.co/csukuangfj) 的公开权重

## 文档

- [结构说明](docs/03-结构说明.md)：分层、数据模型（含全局 `S.me`）、前端函数地图、20 个原生接口、打包与签名、发布检查清单
- [使用说明](docs/04-使用说明.md)：安装、导入、逐项功能、常见问题
- [人设与记忆测试报告](docs/05-人设与记忆测试报告.md)：42 条用例 × 4 轮的一致性数据，1.0.0 → 1.1.0 的对比
- [看图内存压测报告](docs/06-看图内存压测报告.md)：12 次真实视觉编码的内存曲线，2.3 GB 门槛的推导过程
- [多模态模型对照](docs/07-多模态模型对照-Qwen3VL.md)：1B vs Qwen3-VL-2B/4B 的同机测试，三档并存的可行性
