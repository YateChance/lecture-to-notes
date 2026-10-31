# Lecture to Notes

本地处理课程视频，用 Codex 核对板书、编修课堂 record，再生成带来源的讲解报告。当前固定通路面向 **macOS Apple Silicon、教师机位视频、中文课程**。

语义模型固定 **GPT-6.1 Terra / medium**。下载、FFmpeg、VAD、语音识别、OCR、时间轴、缓存和监督由本地代码执行；这些步骤不调用 GPT。课程视频、模型、签名请求和输出保留在本机，不上传 GitHub。

## 已验证结果

动力系统第5周的新视频（约2小时29分钟）已完成下载、30段语音转写、893组抽帧/OCR、5段板书核对、正式 record 和报告。文件及5,479个本地链接检查通过。固定缓存后，重复运行约0.3秒完成验证，未启动ASR、OCR或模型。

详见 [流程说明](docs/WORKFLOW.md) 与 [本次验证记录](docs/WORKFLOW_VALIDATION.md)。主干语义核对不等于逐字听校或逐帧人工校对；具体存疑持续保留。

## 首次准备

需要 Python 3.12+、Node.js 22.12+、FFmpeg/FFprobe、macOS Swift 工具链和已登录的 Codex CLI。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[asr,figures]'
export LECTURE_AGENT_PYTHON="$PWD/.venv/bin/python"
npm ci --ignore-scripts
./bin/lecture-agent doctor
```

本机部署可以直接复用 `~/.local/share/codex-course-tools/venv/bin/python`，无需重复安装。配置在 `configs/default.yaml`。MLX Whisper 模型权重须事先准备在 `runtime.model_cache/asr.model`，本机已有Q4权重；仓库不携带模型，也不把历史环境快照当通用锁文件。Node公式依赖由 `package-lock.json` 固定。

ASR、VAD及Apple Vision OCR在本地运行，无需OpenAI API token。板书编修与报告通过已登录Codex执行，使用该账号的额度。模型设置保存在项目配置和 `.codex/config.toml`，实际调用还会显式传入模型与推理强度。

## 固定工作流 v1

### 1. 初始化课程

先根据实际视频画面确定板书区域；以下参数为示例。

```bash
./bin/lecture-agent pipeline init \
  --subject '示例课程' --week 1 --session 1 \
  --title '核心内容' --date 2026-10-31 \
  --roi 0 0 1920 1080
```

创建 `outputs/示例课程/第01周（1）-核心内容/` 及各阶段目录。已有课程不能被重复初始化。

### 2. 获取并登记原视频

```bash
./bin/lecture-agent download plan \
  --source 'https://example.edu/course/replay' \
  --lesson '示例课程/第01周（1）-核心内容'
```

按 [下载工具工作流](tools/video_download/README.md) 选择方式。网页登录和媒体发现按实际平台处理；签名链接仅放在生成的私有请求JSON。直链HTTP与本地文件导入已实现；HLS/DASH等交由适配器扩展。

```bash
./bin/lecture-agent background start \
  --lesson '示例课程/第01周（1）-核心内容' --stage download -- \
  ./bin/lecture-agent download fetch --request 'outputs/.download_requests/实际请求ID.json'
```

### 3. 一条命令接续处理

确认下载完成后：

```bash
./bin/lecture-agent pipeline plan --lesson '示例课程/第01周（1）-核心内容'
./bin/lecture-agent pipeline run --lesson '示例课程/第01周（1）-核心内容'
```

固定顺序：音轨 → 抽帧 → VAD → ASR → OCR → 板书核对 → record → 报告 → 离线渲染与检查。原视频来自下载登记；未完成阶段接续执行，有效阶段直接复用。板书任务每约30分钟一段，完整转写和对应图片直接作为输入，避免长文件读取截断。

未完成的真实任务默认独立后台运行。脚本每5秒本地监督、每20分钟写摘要，结束或失败立即记录；监督不调用模型。Codex启动长任务后另行登记20分钟聊天心跳并结束当前轮，仅读取摘要，不持续轮询。无变化保持安静，所有任务结束后停止心跳。单独使用CLI只写本地回报文件，聊天通知需App登记成功。

```bash
./bin/lecture-agent background status --lesson '示例课程/第01周（1）-核心内容'
./bin/lecture-agent status --lesson '示例课程/第01周（1）-核心内容'
```

### 4. 验证并固定缓存

新流程成功后自动固定缓存；迁入的已完成课程可手动验证固定：

```bash
./bin/lecture-agent verify
./bin/lecture-agent pipeline freeze
./bin/lecture-agent pipeline run
```

`freeze`检查全部阶段、语义完成门禁、来源与视频SHA-256，记录输入及产物指纹。输入和产物相同的再次运行只验证、不调用模型。若已完成课程的内容发生变化，停止并要求核对、重新固定，避免覆盖人工编修或重复花费。不同视频必须创建独立课程目录，不能在原目录替换素材。

`pipeline run --foreground`用于调试。`render`只重新生成离线HTML。修改代码后不必重新转写整节课。

## 文件结构

```text
src/lecture_agent/         CLI、固定流程、后台监督、Codex执行器、分段板书核对
scripts/                   FFmpeg、VAD、ASR、OCR导出、时间轴、离线渲染
agent/workflow.md          Codex按固定流程操作的简短规范
configs/                   默认配置与历史环境快照
package-lock.json          离线公式渲染依赖锁
tools/video_download/     视频获取策略与可扩展适配器
tests/                    无需调用GPT的回归测试
outputs/<课程>/第NN周（i）-核心内容/
  00_sources/              原视频与下载来源
  01_audio/                音轨
  02_frames/               完整帧、板书裁剪、真实PTS索引
  03_board/                原始OCR、分段核对、板书文字与公式
  04_transcripts/          ASR检查点、原始及清理字幕、审计
  05_documents/            可选资料的缺失说明
  06_timeline/             毫秒事件与时间窗口
  07_record/draft|ready/   候选与正式record
  08_report/               讲解报告、离线HTML与字体
  09_quality/              存疑、完成门禁、检查结果
  _runs/                   模型证据、日志、后台任务与冻结指纹
```

`outputs/`、`legacy/`、虚拟环境、模型、日志和私有请求均不提交。仓库克隆后不包含本机课程产物，因此首次需初始化新课或接入本地已归档课程。当前默认课程指向本机第5周课程，可用 `--lesson`选择其他课程。

## 验证命令

```bash
PYTHONPATH=src "$LECTURE_AGENT_PYTHON" -m unittest discover -s tests -v
"$LECTURE_AGENT_PYTHON" -m unittest discover -s tools/video_download/tests -v
```

测试涵盖未完成门禁、缓存失效、后台成功/失败回报、重复运行零worker、目录保护，以及HTTP下载续传与来源校验。下载测试使用本地服务器和合成视频，不依赖课堂登录。

课件/教材解析、任意平台获取及更完整调度仍按 [实施计划](docs/PLAN.md)扩展。当前流程遇到已配置的辅助资料会明确停止，不会忽略它们后声称已完成融合。
