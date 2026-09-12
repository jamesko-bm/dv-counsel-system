import sys
from pathlib import Path
from fastapi import Request

# 상위 디렉터리를 sys.path에 추가하여 main.py 및 모듈들을 정상 참조할 수 있도록 설정
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from main import app

# Vercel Serverless Rewrites 경로 보정 미들웨어
@app.middleware("http")
async def fix_vercel_rewrites_path(request: Request, call_next):
    # Vercel은 rewrite 시 원래 사용자가 요청한 URL을 x-matched-path 헤더에 전달합니다.
    matched_path = request.headers.get("x-matched-path")
    invoke_path = request.headers.get("x-invoke-path")

    if matched_path:
        # 쿼리 스트링 분리
        raw_path = matched_path.split("?")[0]
        # 만약 /api/index.py 로 rewrites된 경우 원본 요청 처리
        if raw_path in ["/api/index.py", "/api/index", "/api"]:
            request.scope["path"] = "/"
        else:
            request.scope["path"] = raw_path
    elif invoke_path:
        raw_path = invoke_path.split("?")[0]
        if raw_path in ["/api/index.py", "/api/index", "/api"]:
            request.scope["path"] = "/"
        else:
            request.scope["path"] = raw_path
    else:
        # 헤더가 없는 경우 기본 보정
        current_path = request.scope.get("path", "")
        if current_path in ["/api/index.py", "/api/index", "/api"]:
            request.scope["path"] = "/"

    response = await call_next(request)
    return response
