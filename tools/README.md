# 可复用工具

工具可以独立调用，也可以由项目CLI或Codex工作流调用。网站差异放在工作流或适配器中，不在主流水线硬编码某个页面的下载方式。

| 工具 | 入口 | 用途 |
|---|---|---|
| [video_download](video_download/README.md) | `./bin/lecture-agent download` 或 `python3 tools/video_download/download.py` | 判断下载策略、直链视频下载、浏览器下载后的文件导入、来源登记与验证 |

每个工具应有说明、输入输出协议、可运行入口和明确的能力边界。下载完成只代表原素材准备完成，不自动代表转写、编修或报告已经完成。
