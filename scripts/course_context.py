"""Shared path resolution for tools; never infer a lesson from the script directory."""
from pathlib import Path
import argparse
import os
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((PROJECT_ROOT / 'configs/default.yaml').read_text())
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument('--lesson', default=os.environ.get('LECTURE_AGENT_LESSON', CONFIG['default_lesson']))
options, _ = parser.parse_known_args()
requested = Path(options.lesson).expanduser()
LESSON_ROOT = (requested if requested.is_absolute() else PROJECT_ROOT / 'outputs' / requested).resolve()
if not (LESSON_ROOT / 'lesson.yaml').exists():
    raise SystemExit(f'找不到课程配置: {LESSON_ROOT / "lesson.yaml"}')
LESSON = yaml.safe_load((LESSON_ROOT / 'lesson.yaml').read_text())
MODEL_CACHE = Path(CONFIG['runtime']['model_cache']).expanduser()
MODEL_PATH = MODEL_CACHE / LESSON.get('asr', {}).get('model', CONFIG['asr']['model'])
