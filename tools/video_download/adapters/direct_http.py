"""The verified direct media URL path, using curl without loading ~/.curlrc."""
from pathlib import Path
import os
import subprocess
import tempfile
from urllib.parse import urlsplit

from common import DownloadError, http_url, private_json


def escaped(value):
    if any(c in str(value) for c in '\r\n\x00'):
        raise DownloadError('下载配置不接受换行或控制字符。')
    return str(value).replace('\\', '\\\\').replace('"', '\\"')


def fetch(request, part, state_path, state):
    url = http_url(request['media_url'])
    if Path(urlsplit(url).path).suffix.lower() in {'.m3u8', '.mpd'}:
        raise DownloadError('这是流媒体清单，请使用相应适配器，不能当直链视频保存。')
    resume = part.exists() and part.stat().st_size > 0
    if resume and state.get('resume_blocked'):
        raise DownloadError('服务器的资源身份或续传响应已改变，旧分段不能继续；请使用--restart。')
    if resume and (not state.get('etag') or state['etag'].startswith('W/')):
        raise DownloadError('已有未完成文件，但没有ETag用于确认续传身份；可显式--restart重新开始。')
    with tempfile.TemporaryDirectory(prefix='lecture-download-') as temporary:
        config = Path(temporary) / 'curl.conf'
        headers = Path(temporary) / 'headers.txt'
        fd = os.open(headers, os.O_WRONLY | os.O_CREAT, 0o600)
        os.close(fd)
        lines = [f'url = "{escaped(url)}"', f'output = "{escaped(part)}"',
                 f'dump-header = "{escaped(headers)}"', 'location', 'fail', 'globoff',
                 'proto = "=http,https"', 'proto-redir = "=http,https"',
                 'max-redirs = 5', 'connect-timeout = 20', 'speed-limit = 1024',
                 'speed-time = 120', 'retry = 2', 'progress-bar']
        if resume:
            lines += ['continue-at = "-"', f'header = "If-Range: {escaped(state["etag"])}"']
        fd = os.open(config, os.O_WRONLY | os.O_CREAT, 0o600)
        with os.fdopen(fd, 'w') as handle:
            handle.write('\n'.join(lines) + '\n')
        try:
            result = subprocess.run(['curl', '--disable', '--config', str(config)])
        except OSError as error:
            raise DownloadError('找不到curl。') from error
        finally:
            # Raw headers can contain cookies or signed redirects: never persist them.
            text = headers.read_text(errors='replace')
            blocks = text.replace('\r\n', '\n').strip().split('\n\n')
            final = blocks[-1] if blocks else ''
            fields = {}
            for line in final.splitlines()[1:]:
                if ':' in line:
                    key, value = line.split(':', 1)
                    fields[key.lower().strip()] = value.strip()
            status_line = final.splitlines()[0] if final.splitlines() else ''
            resource_changed = resume and (
                (fields.get('etag') and fields['etag'] != state.get('etag'))
                or (status_line.startswith('HTTP/') and ' 200 ' in status_line))
            if resource_changed:
                state['resume_blocked'] = True
            elif fields.get('etag'):
                state['etag'] = fields['etag']
            state['content_type'] = fields.get('content-type', '')
            private_json(state_path, state)
        if state.get('resume_blocked'):
            raise DownloadError('服务器返回的资源身份或续传响应已改变；旧分段保留，请显式--restart。')
        if result.returncode:
            raise DownloadError(f'curl下载未完成（退出码{result.returncode}）。保留分段；链接可能过期、需要登录或不支持续传。')
        content_type = state.get('content_type', '').split(';')[0].strip().lower()
        if content_type in {'text/html', 'application/xhtml+xml', 'application/json',
                            'application/vnd.apple.mpegurl', 'application/x-mpegurl', 'application/dash+xml'}:
            raise DownloadError('服务器返回的是页面、接口结果或播放清单，不是视频文件。')
    return {'adapter': 'direct_http', 'resumed': resume, 'content_type': state.get('content_type')}
