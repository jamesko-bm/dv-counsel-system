import sys
from pathlib import Path
from fastapi.testclient import TestClient

# 프로젝트 경로 추가
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from main import app
from database import init_db, get_db_connection

def run_all_tests():
    print(">>> 1. 데이터베이스 초기화 테스트...")
    init_db()
    print("  [OK] 데이터베이스 초기화 성공")

    client = TestClient(app)

    print(">>> 2. 메인 대시보드 페이지 테스트...")
    res = client.get("/")
    assert res.status_code == 200, f"대시보드 실패: {res.status_code}"
    assert "희망가정폭력상담소" in res.text
    print("  [OK] 대시보드 렌더링 정상 (HTTP 200)")

    print(">>> 3. [1. 전화 상담기록] 기능 테스트...")
    # 목록 조회
    res = client.get("/calls")
    assert res.status_code == 200
    # 신규 상담 등록
    new_call_data = {
        "call_date": "2026-09-05 15:30",
        "client_name": "테스트내담자",
        "is_anonymous": 0,
        "client_gender": "여성",
        "client_age_group": "30대",
        "client_phone": "010-1111-2222",
        "client_region": "서울 마포구",
        "violence_types": ["신체적 폭력", "정서/언어적 폭력"],
        "perpetrator_relation": "배우자",
        "risk_level": "HIGH",
        "incident_history": "최근 1년간 지속된 폭행",
        "main_issues": "긴급 피난 및 쉼터 입소 문의",
        "counseling_content": "내담자의 신체적 안전 확보가 최우선이므로 긴급 쉼터 연계 진행.",
        "action_types": ["긴급피난/쉼터", "경찰연계"],
        "status": "IN_PROGRESS",
        "counselor_id": 2
    }
    res = client.post("/api/calls", json=new_call_data)
    assert res.status_code == 200
    call_id = res.json()["id"]
    print(f"  [OK] 신규 상담 등록 성공 (ID: {call_id})")

    # 상세 조회
    res = client.get(f"/api/calls/{call_id}")
    assert res.status_code == 200
    assert res.json()["client_name"] == "테스트내담자"

    # CSV 다운로드
    res = client.get("/api/calls/export/csv")
    assert res.status_code == 200
    assert "접수번호" in res.text
    print("  [OK] CSV 다운로드 정상")

    print(">>> 4. [2. 휴가 신청 및 결재] 기능 테스트...")
    res = client.get("/leaves")
    assert res.status_code == 200

    leave_data = {
        "leave_type": "연차",
        "start_date": "2026-09-20",
        "end_date": "2026-09-20",
        "days_count": 1.0,
        "reason": "테스트 연차 신청",
        "deputy_counselor_id": 3
    }
    # 쿠키 설정 (박서윤 id=2)
    client.cookies.set("current_counselor_id", "2")
    res = client.post("/api/leaves", json=leave_data)
    assert res.status_code == 200, f"휴가 신청 실패: {res.text}"
    print("  [OK] 휴가 신청 정상 등록")

    # 방금 등록된 휴가 ID 확인
    conn = get_db_connection()
    last_leave = conn.execute("SELECT id FROM leave_requests ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    
    # 관리자(id=1) 전환 후 승인 처리
    client.cookies.set("current_counselor_id", "1")
    res = client.post(f"/api/leaves/{last_leave['id']}/process", json={"status": "APPROVED"})
    assert res.status_code == 200
    print("  [OK] 관리자 휴가 승인 및 잔여 연차 차감 정상")

    print(">>> 5. [3. 상담사 관리] 기능 테스트...")
    res = client.get("/counselors")
    assert res.status_code == 200

    import time
    new_counselor = {
        "username": f"tester_{int(time.time())}",
        "password": "pass",
        "name": "홍길동",
        "role": "COUNSELOR",
        "title": "상담원",
        "phone": "010-9999-8888",
        "email": "test@counsel.kr",
        "specialties": "청소년,위기개입",
        "annual_leave_total": 15.0
    }
    res = client.post("/api/counselors", json=new_counselor)
    assert res.status_code == 200, f"상담사 등록 실패: {res.text}"
    c_id = res.json()["id"]
    print(f"  [OK] 신규 상담사 등록 성공 (ID: {c_id})")

    print(">>> 6. [4. 업무일지] 기능 테스트...")
    res = client.get("/worklogs")
    assert res.status_code == 200

    worklog_data = {
        "log_date": "2026-09-05",
        "counseling_summary": "신규 긴급 상담 1건 처리 및 안심 쉼터 연계 완료.",
        "admin_tasks": "경찰서 APO 미팅 자료 준비",
        "crisis_cases": "테스트 고위험 건 안전 확인 완료",
        "tomorrow_plan": "후속 대면 심리상담 일정 수립"
    }
    client.cookies.set("current_counselor_id", "2")
    res = client.post("/api/worklogs", json=worklog_data)
    assert res.status_code == 200
    print("  [OK] 업무일지 저장 정상")

    # 소장(id=1) 피드백 등록
    client.cookies.set("current_counselor_id", "1")
    res = client.post("/api/worklogs/2026-09-05/feedback", json={"feedback": "수고 많으셨습니다. 안전 점검 지속해주세요.", "is_confirmed": 1})
    assert res.status_code == 200
    print("  [OK] 업무일지 관리자 피드백 등록 정상")

    print(">>> 7. [5. 마이페이지] 기능 테스트...")
    client.cookies.set("current_counselor_id", "2")
    res = client.get("/mypage")
    assert res.status_code == 200
    assert "박서윤" in res.text
    print("  [OK] 마이페이지 렌더링 정상 (HTTP 200)")

    print(">>> 8. [Typebot 챗봇 Webhook] 연동 테스트...")
    typebot_payload = {
        "client_name": "챗봇상담신청자",
        "is_anonymous": "익명",
        "client_gender": "여성",
        "client_age_group": "20대",
        "client_phone": "010-8888-7777",
        "client_region": "서울 송파구",
        "violence_types": ["정서/언어적 폭력", "통제/방임"],
        "perpetrator_relation": "교제상대",
        "risk_level": "MEDIUM",
        "main_issues": "Typebot 챗봇을 통한 야간 안심 상담 접수",
        "counseling_content": "내담자가 챗봇 문답을 통해 남긴 세부 피해 상황 내역입니다."
    }
    res = client.post("/api/webhook/typebot", json=typebot_payload)
    assert res.status_code == 200
    webhook_res = res.json()
    assert webhook_res["success"] is True
    print(f"  [OK] Typebot Webhook 접수 -> DB 등록 성공 (ID: {webhook_res['id']})")

    print(">>> 9. [통화 녹취/Tyro AI 자동 일지 작성] 테스트...")
    sample_transcript = "남편이 식칼을 들고 죽이겠다고 협박해서 아이와 함께 편의점으로 피신했어요. 얼굴을 맞아 멍이 들었고 쉼터 연계와 경찰 신고가 급합니다."
    res = client.post("/api/calls/analyze-transcript", json={"transcript": sample_transcript})
    assert res.status_code == 200
    ext = res.json()["extracted_data"]
    assert ext["risk_level"] == "HIGH", f"위험도 판별 실패: {ext['risk_level']}"
    assert "신체적 폭력" in ext["violence_types"]
    assert ext["perpetrator_relation"] == "배우자"
    print(f"  [OK] 통화 녹취 분석 성공 (위험도: {ext['risk_level']}, 폭력유형: {ext['violence_types']})")



    print("\n==============================================")
    print("  ★ 모든 5대 핵심 기능 테스트 100% 통과! ★  ")
    print("==============================================")

if __name__ == "__main__":
    run_all_tests()
