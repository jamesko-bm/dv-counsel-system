import uvicorn

if __name__ == "__main__":
    print("=====================================================")
    print("  희망가정폭력상담소 관리 시스템 (DV Counsel System)")
    print("  서버 주소: http://127.0.0.1:8000")
    print("=====================================================")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
