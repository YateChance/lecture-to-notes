# 视频下载工作流与工具

将“发现可用下载方式”和“执行文件传输”分开。适配器负责传输，站点profile描述发现步骤，Codex按实际浏览器页面选择方式。

## 当前能力

| 来源情况 | 处理方式 | 实现状态 |
|---|---|---|
| 直接HTTP(S)视频链接，包括可直接访问的签名MP4 | direct_http：curl下载，校验后登记 | 已实现并以本地HTTP视频测试 |
| 已由浏览器、平台客户端或人工下载的本地文件 | local_file：复制、校验、登记 | 已实现 |
| 登录后的普通课程页面 | Codex查看正常下载入口或可见播放器媒体源，然后选择适配器 | 工作流已提取；不是CLI自动登录爬虫 |
| blob媒体地址 | 浏览器原生下载或平台导出，保存文件后local_file导入 | 明确交接，不把blob当网络地址 |
| HLS、DASH清单 | 使用合适的流媒体下载器后导入，或新增适配器 | 首版没有内置该传输后端，不把清单保存成MP4 |
| 平台专用下载方式 | 对应工具或平台客户端，之后导入；可扩展适配器 | 逐站点适配，未承诺通用支持 |

登录、验证码、访问权限和受保护媒体按站点正常流程处理。工具不提取Cookie、不读取浏览器凭据、不关闭证书校验，也不执行DRM解密。

## 使用步骤

在项目根目录，先生成策略与私有请求文件：

```bash
./bin/lecture-agent download plan \
  --source 'https://example.edu/course/replay' \
  --lesson '动力系统/第03周（1）-待整理'
```

输出包括所匹配的profile、需要哪种发现步骤，以及 `outputs/.download_requests/<随机ID>.json` 的路径。`plan`不会访问网站或开始传输；会准备输出目录。请求文件权限为0600，整个outputs已被Git忽略。

如果给的是直接媒体链接，会生成 `adapter: direct_http` 的请求。给的是网页，则先按[浏览器发现流程](workflows/browser_discovery.md)找到可用方式，再编辑请求中的以下字段：

```json
{
  "schema_version": "1.0",
  "lesson": "动力系统/第03周（1）-待整理",
  "filename": "teacher.mp4",
  "adapter": "direct_http",
  "page_url": "https://example.edu/course/replay",
  "media_url": "填写本次浏览器实际发现的媒体地址",
  "local_file": null,
  "profile": "generic",
  "stream_role": "teacher",
  "expected": {
    "duration_seconds": 8912,
    "duration_tolerance_seconds": 3
  }
}
```

该JSON仅说明字段，不是可以直接下载的地址。若不知道预期时长，使用空的 `expected: {}`，不编造时长。

字段协议见 [request.schema.json](request.schema.json)。含签名的媒体地址优先直接填写私有JSON，不放进共享命令示例或公开配置。

随后执行：

```bash
./bin/lecture-agent download fetch \
  --request 'outputs/.download_requests/实际请求ID.json'
```

已用其他方式下载到本地的文件，可直接用本地路径生成计划，再执行同样的fetch：

```bash
./bin/lecture-agent download plan \
  --source '/本地路径/已下载的视频.mp4' \
  --lesson '动力系统/第03周（1）-待整理'
```

## 输出与校验

```text
outputs/<课程>/<课次>/00_sources/
├── video/
│   ├── teacher.mp4                 # 验证通过后才生成正式文件
│   ├── teacher.mp4.part            # 失败或中断时保留
│   └── teacher.mp4.part.json       # 续传身份和状态，不存媒体URL
├── downloads/
│   ├── <source_id>.json            # 下载回执、实际容器信息和SHA-256
│   └── attempts/                   # 显式重下时归档本工具的旧分段
└── sources.jsonl                   # 追加来源记录，不覆盖已有来源
```

工具检查：响应不是登录页或清单、ffprobe能解析视频轨与正时长、可选预期大小/时长一致，并计算文件SHA-256。ffprobe只读取本地文件协议，不在校验时跟随清单访问其他网络资源。检查不等同于逐帧解码整部视频。

最终视频存在时始终拒绝覆写。相同目标有下载锁时拒绝并发写入。没有本工具状态记录的旧分段不自动接管。

HTTP续传需要同一请求身份、服务器支持Range和可用于If-Range的强ETag。资源改变或服务器不支持续传时暂停，不拼接成看似完成的损坏文件。可以显式重下：

```bash
./bin/lecture-agent download fetch --request '实际请求文件.json' --restart
```

`--restart`将本工具拥有的旧分段归档后重下，不覆盖已经完成的视频。链接签名过期时先回到浏览器重新发现地址，再更新私有请求文件；不能反复用旧链接重试。

下载时curl显示传输进度；按Ctrl+C暂停，未完成分段保留。若进程被强制终止留下锁，先核对锁中的PID与实际任务，确认任务已退出后再处理锁，不盲目启动第二个写入者。

完整媒体地址只保存在私有请求文件和临时curl配置中。完成回执保留媒体源域名、请求身份哈希及去除查询值后的页面引用，不保存完整签名媒体URL或原始HTTP响应头。请求文件完成使用后可由用户清理；不要提交或分享它。

下载工具不创建完整lesson.yaml，也不自动把新视频选成已有课程的主视频；这些属于后续素材登记阶段。教师流、PPT流应使用不同文件名和stream_role登记。

## 目录结构

```text
tools/video_download/
├── download.py                    # plan、fetch、adapters
├── common.py                      # 请求、路径、校验和回执
├── adapters/
│   ├── direct_http.py
│   └── local_file.py
├── profiles/
│   ├── generic.json
│   └── buaa_classroom.json
├── workflows/
│   ├── browser_discovery.md
│   └── add_adapter.md
└── tests/test_download.py
```

北航课堂案例见[浏览器发现流程](workflows/browser_discovery.md)。profile描述站点经验，不保存该次课堂的临时签名，不保证所有回放使用同一传输方式。

实现参考：[curl官方手册](https://curl.se/docs/manpage.html)。媒体校验参数可通过本机 `ffprobe -h` 检查。

验证命令：

```bash
python3 -m unittest discover -s tools/video_download/tests -v
```

测试使用本地HTTP服务器和1秒合成视频，不重新下载已完成课程。
