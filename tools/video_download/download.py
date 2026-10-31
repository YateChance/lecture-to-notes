#!/usr/bin/env python3
"""Discover a route, fetch through an explicit adapter, and register verified media."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import os
import shutil
import sys
from urllib.parse import urlsplit, urlunsplit
import uuid

from adapters import ADAPTERS
from common import (PROJECT, VIDEO_SUFFIXES, DownloadError, destination, http_url,
                    now, private_json, probe_video, redacted_url, sha256)


def profile_for(source):
    host = urlsplit(source).hostname
    generic = None
    for file in sorted((Path(__file__).parent / 'profiles').glob('*.json')):
        profile = json.loads(file.read_text())
        if profile['id'] == 'generic':
            generic = profile
        if host and host in profile.get('page_hosts', []):
            return profile
    return generic


def make_plan(source, lesson, project=PROJECT):
    profile = profile_for(source)
    suffix = Path(urlsplit(source).path).suffix.lower()
    request = {'schema_version': '1.0', 'lesson': lesson, 'filename': 'lecture.mp4',
               'adapter': None, 'page_url': None, 'media_url': None, 'local_file': None,
               'profile': profile['id'], 'stream_role': 'unspecified', 'expected': {}}
    if source.startswith(('http://', 'https://')):
        http_url(source)
        if suffix in VIDEO_SUFFIXES:
            route = 'ready_for_direct_http_verification'
            request.update(adapter='direct_http', media_url=source, filename='lecture' + suffix)
        elif suffix in {'.m3u8', '.mpd'}:
            route = 'requires_stream_adapter'
            request['page_url'] = source
        else:
            route = 'requires_browser_discovery'
            request['page_url'] = source
    elif source.startswith('blob:'):
        route = 'requires_browser_native_download'
    else:
        local = Path(source).expanduser().resolve()
        if not local.is_file():
            raise DownloadError('source不是HTTP(S)页面、媒体链接或存在的本地文件。')
        route = 'ready_for_local_import_verification'
        request.update(adapter='local_file', local_file=str(local), filename='lecture' + local.suffix.lower())
    # Validate output location even when browser discovery is still pending.
    destination(request, project)
    file = project / 'outputs/.download_requests' / f'{uuid.uuid4().hex}.json'
    private_json(file, request)
    return {'route': route, 'profile': profile['id'], 'request_file': str(file),
            'supported_adapters': sorted(ADAPTERS), 'workflow': profile['workflow'],
            'note': 'plan只生成策略和私有请求文件，不会访问网站或开始下载。'}


def request_identity(request):
    source = request.get('media_url') if request.get('adapter') == 'direct_http' else request.get('local_file')
    return hashlib.sha256(json.dumps({'adapter': request.get('adapter'), 'source': source}, sort_keys=True).encode()).hexdigest()


def perform(request, project=PROJECT, restart=False):
    if not isinstance(request, dict):
        raise DownloadError('请求必须是JSON对象。')
    allowed = {'schema_version', 'lesson', 'filename', 'adapter', 'page_url', 'media_url',
               'local_file', 'profile', 'stream_role', 'expected'}
    if set(request) - allowed:
        raise DownloadError('请求含未支持的字段；不接受Cookie或认证header，请使用浏览器正常下载后导入。')
    expected = request.get('expected', {})
    if not isinstance(expected, dict) or set(expected) - {'bytes', 'duration_seconds', 'duration_tolerance_seconds'}:
        raise DownloadError('expected字段格式不正确。')
    for key, value in expected.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise DownloadError('预期大小、时长和容差必须是有限非负数字。')
        if key != 'duration_tolerance_seconds' and value == 0:
            raise DownloadError('预期大小和时长必须大于零。')
    if request.get('schema_version') != '1.0':
        raise DownloadError('不支持该请求版本。')
    adapter = request.get('adapter')
    if adapter not in ADAPTERS:
        raise DownloadError('尚未选定已实现的下载适配器；请先完成浏览器发现或手动下载，再用local_file导入。')
    if adapter == 'direct_http':
        http_url(request.get('media_url'))
    elif not isinstance(request.get('local_file'), str) or not request['local_file'].strip():
        raise DownloadError('local_file需要本地文件路径。')
    lesson, target = destination(request, project)
    part = target.with_name(target.name + '.part')
    state_path = target.with_name(target.name + '.part.json')
    lock = target.with_name(target.name + '.download.lock')
    if target.exists() or target.is_symlink():
        raise DownloadError('目标视频已存在，不会覆写；请使用其他文件名。')
    if part.is_symlink() or state_path.is_symlink():
        raise DownloadError('拒绝使用符号链接作为临时下载文件。')
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise DownloadError('该文件已有下载锁。先检查对应任务；不要同时下载到同一目标。') from error
    with os.fdopen(fd, 'w') as handle:
        json.dump({'pid': os.getpid(), 'started_at': now()}, handle)
    state = None
    try:
        identity = request_identity(request)
        if part.exists() and not state_path.exists():
            raise DownloadError('已有未知来源的.part文件，不能自动覆盖或续传。')
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        if restart and state:
            archive = lesson / '00_sources/downloads/attempts' / uuid.uuid4().hex
            archive.mkdir(parents=True)
            if part.exists():
                shutil.move(str(part), archive / part.name)
            shutil.move(str(state_path), archive / state_path.name)
            state = {}
        if state and state.get('identity') != identity:
            raise DownloadError('媒体来源已改变，不能将新地址接到旧文件；确认需要重下时使用--restart，旧分段会归档。')
        state.update(identity=identity, adapter=adapter, status='running', updated_at=now())
        private_json(state_path, state)
        print(f'下载目标：{target}\n临时文件：{part}', flush=True)
        info = ADAPTERS[adapter](request, part, state_path, state)
        if not part.is_file() or not part.stat().st_size:
            raise DownloadError('没有取得视频数据。')
        os.chmod(part, 0o600)
        probe = probe_video(part, request.get('expected'))
        checksum = sha256(part)
        media = urlsplit(request.get('media_url') or '')
        receipt = {'schema_version': '1.0', 'status': 'complete', 'downloaded_at': now(),
                   'source_id': 'video_' + checksum[:16] + '_' + hashlib.sha256(target.name.encode()).hexdigest()[:8],
                   'role': 'video', 'path': str(target.relative_to(lesson)), 'sha256': checksum,
                   'bytes': part.stat().st_size, 'adapter': adapter,
                   'profile': request.get('profile', 'generic'),
                   'stream_role': request.get('stream_role', 'unspecified'),
                   'page_url_redacted': redacted_url(request.get('page_url')),
                   'media_origin': urlunsplit((media.scheme, media.netloc, '', '', '')) if media.netloc else None,
                   'media_identity_sha256': identity, 'probe': probe, 'transport': info,
                   'verification_scope': '容器、视频轨、时长、可选预期大小/时长及SHA-256；未逐帧完整解码。'}
        # Same filesystem: link() atomically refuses any existing final destination.
        os.link(part, target)
        part.unlink()
        receipts = lesson / '00_sources/downloads'
        private_json(receipts / (receipt['source_id'] + '.json'), receipt)
        sources = lesson / '00_sources/sources.jsonl'
        with sources.open('a') as handle:
            handle.write(json.dumps(receipt, ensure_ascii=False) + '\n')
        state.update(status='complete', receipt=str((receipts / (receipt['source_id'] + '.json')).relative_to(lesson)))
        private_json(state_path, state)
        state_path.unlink()
        print('校验并登记完成。', flush=True)
        return receipt
    except (Exception, KeyboardInterrupt) as error:
        if state is not None:
            state.update(status='paused' if isinstance(error, KeyboardInterrupt) else 'failed', updated_at=now())
            # Exceptions may carry URLs: keep only the type in persistent state.
            state['error_type'] = type(error).__name__
            private_json(state_path, state)
        raise
    finally:
        lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='视频下载策略、直链获取与本地视频导入。')
    sub = parser.add_subparsers(dest='command', required=True)
    plan = sub.add_parser('plan', help='判断路径并生成私有请求文件，不开始下载')
    plan.add_argument('--source', required=True)
    plan.add_argument('--lesson', required=True)
    fetch = sub.add_parser('fetch', help='按已准备的请求下载并校验')
    fetch.add_argument('--request', type=Path, required=True)
    fetch.add_argument('--restart', action='store_true', help='归档本工具的旧分段后重新下载；不会覆盖最终视频')
    sub.add_parser('adapters', help='列出已实现的适配器')
    args = parser.parse_args()
    if args.command == 'adapters':
        print(json.dumps({'implemented': sorted(ADAPTERS), 'handoff': ['browser_discovery', 'hls', 'dash', 'platform_specific']}, indent=2))
    elif args.command == 'plan':
        print(json.dumps(make_plan(args.source, args.lesson), ensure_ascii=False, indent=2))
    else:
        request = json.loads(args.request.read_text())
        print(json.dumps(perform(request, restart=args.restart), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (DownloadError, ValueError, KeyError, OSError) as error:
        print(f'下载未完成：{error}', file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        print('已暂停；本工具拥有的未完成分段保留。', file=sys.stderr)
        raise SystemExit(130)
