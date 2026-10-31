"""Shared download contracts and local verification. No browser credentials involved."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import subprocess
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

PROJECT = Path(__file__).resolve().parents[2]
VIDEO_SUFFIXES = {'.mp4', '.mkv', '.webm', '.mov', '.m4v', '.ts', '.avi'}


class DownloadError(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def private_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


def http_url(value):
    if not isinstance(value, str) or any(c in value for c in '\r\n\x00'):
        raise DownloadError('需要有效HTTP(S)地址，不接受换行或控制字符。')
    parsed = urlsplit(value)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
        raise DownloadError('仅支持不内嵌用户名密码的HTTP(S)地址。')
    return value


def redacted_url(value):
    if not value:
        return None
    parsed = urlsplit(value)
    # Signed tokens are sometimes part of the path as well as the query.
    path = parsed.path
    for marker in ['/token/', '/auth/', '/signature/']:
        if marker in path.lower():
            path = path[:path.lower().index(marker)] + '/[redacted]'
    query = urlencode([(key, '[redacted]') for key, _ in parse_qsl(parsed.query, keep_blank_values=True)])
    return urlunsplit((parsed.scheme, parsed.netloc.rsplit('@', 1)[-1], path, query, ''))


def destination(request, project=PROJECT):
    relative = Path(request.get('lesson', ''))
    if not str(request.get('lesson', '')).strip() or relative.is_absolute() or '..' in relative.parts:
        raise DownloadError('lesson必须为outputs下的课程相对路径。')
    outputs = (project / 'outputs').resolve()
    lesson = (outputs / relative).resolve()
    if not lesson.is_relative_to(outputs) or lesson == outputs:
        raise DownloadError('课程目录必须位于项目outputs内部。')
    name = request.get('filename', 'lecture.mp4')
    if not isinstance(name, str) or Path(name).name != name or Path(name).suffix.lower() not in VIDEO_SUFFIXES:
        raise DownloadError('filename必须是单个视频文件名，例如lecture.mp4。')
    folder = lesson / '00_sources/video'
    folder.mkdir(parents=True, exist_ok=True)
    folder = folder.resolve()
    if not folder.is_relative_to(outputs):
        raise DownloadError('视频目录不能通过符号链接写到outputs之外。')
    return lesson, folder / name


def probe_video(path, expected=None):
    try:
        result = subprocess.run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe', '-show_entries',
            'format=duration,size,format_name:stream=codec_type,codec_name,width,height',
            '-of', 'json', str(path)], text=True, capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DownloadError('无法运行ffprobe，请先安装或检查FFmpeg。') from error
    try:
        data = json.loads(result.stdout)
        duration = float(data.get('format', {}).get('duration', 0))
    except (ValueError, TypeError):
        raise DownloadError('下载结果不能解析为有效视频。')
    if result.returncode or not math.isfinite(duration) or duration <= 0 or not any(
            stream.get('codec_type') == 'video' for stream in data.get('streams', [])):
        raise DownloadError('下载结果缺少有效视频轨或时长，未登记为完成。')
    if data.get('format', {}).get('format_name') in {'hls', 'dash', 'concat'}:
        raise DownloadError('下载结果是播放清单而不是完整视频容器。')
    expected = expected or {}
    if expected.get('bytes') is not None and path.stat().st_size != int(expected['bytes']):
        raise DownloadError('文件大小与预期不一致，未登记为完成。')
    if expected.get('duration_seconds') is not None:
        wanted = float(expected['duration_seconds'])
        tolerance = float(expected.get('duration_tolerance_seconds', max(2, wanted * .01)))
        if abs(duration - wanted) > tolerance:
            raise DownloadError('视频时长与预期不一致，未登记为完成。')
    return data
