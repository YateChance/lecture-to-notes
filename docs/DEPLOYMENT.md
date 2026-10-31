# 文件部署记录

部署日期：2026年10月31日，Asia/Manila。

## 工作位置

唯一后续工作目录：`/Users/wens/Work/CC/lecture-to-notes`。

部署前目标目录为空，没有覆盖既有项目文件。原Downloads材料和旧规划目录保留；本项目使用复制后的材料，后续不再操作旧课程目录。

## 已部署内容

- 已确认的项目计划、AGENTS.md、README、配置和Python项目声明。
- 维护CLI：doctor、status、paths、render、verify。
- 路径已适配的ASR、VAD、清理、OCR导出、数学图与HTML渲染脚本。
- 原始代码的只读存档，避免课程特定文本和旧路径被误用作新课程执行器。
- 课程目录：`outputs/动力系统/第02周（1）-一维系统分岔`。
- 原视频、音轨、890张全画面、890张板书图、OCR原文、30段完整转写、清理审计、主干编修record和课程报告。
- 新生成4175条时间索引事件，包含3285条清理版语音片段与890条帧事件，按30个时间窗口汇总。时间归并不等于逐条语义对齐。
- 原视频与音轨迁移前后的SHA-256一致；具体校验值保存在课程 `_runs/import_20261031/migration_complete.json`。

课件和教材未提供，配置明确标为空；没有伪造对应的解析结果。

## 运行依赖

复用共享Python环境与两个已下载的Whisper模型，不重复复制模型权重。共享依赖不属于课程输出；项目CLI仍可通过环境变量切换运行Python。

现有环境快照：`configs/imported-environment.lock.txt`。FFmpeg、FFprobe、Node和Swift使用本机安装。

## 验证范围

部署检查包含：CLI入口可用、环境诊断、路径读取、从新Markdown位置重新生成三份HTML、图片和ASR分段数量、音轨时间范围，以及本地报告、图片和公式字体引用。

没有重新运行整节课的ASR或OCR，以免重复消耗算力并覆盖已校订成果。完整模块化agent与新课程端到端流程仍按照PLAN实施。
