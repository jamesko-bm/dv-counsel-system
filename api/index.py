import sys
from pathlib import Path

# 상위 디렉터리를 sys.path에 추가하여 main.py 및 모듈들을 정상 참조할 수 있도록 설정
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from main import app
