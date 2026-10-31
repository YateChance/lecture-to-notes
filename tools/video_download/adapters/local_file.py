"""Register a browser/native download without depending on its site's mechanism."""
from pathlib import Path
import shutil

from common import DownloadError


def fetch(request, part, state_path, state):
    source = Path(request.get('local_file', '')).expanduser().resolve()
    if not source.is_file():
        raise DownloadError('找不到已下载的本地视频文件。')
    if part.exists():
        raise DownloadError('本地导入已有未完成副本，请使用--restart。')
    shutil.copy2(source, part)
    return {'adapter': 'local_file', 'original_name': source.name}
