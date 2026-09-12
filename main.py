import os
import json
import csv
import io
from datetime import datetime, date, timedelta
from typing import Optional, List
from pathlib import Path

from fastapi import FastAPI, Request, Response, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from database import get_db_connection, init_db, get_db_status_info
import models

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="가정폭력 상담소 관리 시스템")

# 정적 파일 및 템플릿 마운트
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["get_db_status"] = get_db_status_info

# 서버 시작 시 DB 초기화
@app.on_event("startup")
def startup_event():
    init_db()

# 현재 사용자 획득 헬퍼 (쿠키 기반, 기본값은 선임상담사 id=2 또는 센터장 id=1)
def get_current_counselor(request: Request):
    counselor_id = request.cookies.get("current_counselor_id")
    conn = get_db_connection()
    counselor = None
    if counselor_id:
        counselor = conn.execute("SELECT * FROM counselors WHERE id = ? AND is_active = 1", (counselor_id,)).fetchone()
    
    if not counselor:
        # 기본값: 박서윤 선임상담사 (id: 2) 또는 첫 번째 상담사
        counselor = conn.execute("SELECT * FROM counselors ORDER BY id ASC LIMIT 1").fetchone()
    
    conn.close()
    return dict(counselor) if counselor else None

def get_all_active_counselors():
    conn = get_db_connection()
    counselors = [dict(r) for r in conn.execute("SELECT * FROM counselors WHERE is_active = 1 ORDER BY role = 'DIRECTOR' DESC, id ASC").fetchall()]
    conn.close()
    return counselors

# ----------------- 페이지 라우트 -----------------

@app.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    user = get_current_counselor(request)
    all_users = get_all_active_counselors()
    conn = get_db_connection()

    # 요약 통계
    today_str = date.today().strftime("%Y-%m-%d")
    today_calls = conn.execute("SELECT COUNT(*) FROM call_logs WHERE call_date LIKE ?", (f"{today_str}%",)).fetchone()[0]
    total_calls = conn.execute("SELECT COUNT(*) FROM call_logs").fetchone()[0]
    high_risk_count = conn.execute("SELECT COUNT(*) FROM call_logs WHERE risk_level = 'HIGH'").fetchone()[0]
    pending_leaves = conn.execute("SELECT COUNT(*) FROM leave_requests WHERE status = 'PENDING'").fetchone()[0]
    
    # 최근 긴급/위기 상담 5건
    recent_high_risk = [dict(r) for r in conn.execute(
        """SELECT c.*, cs.name as counselor_name 
           FROM call_logs c 
           LEFT JOIN counselors cs ON c.counselor_id = cs.id 
           WHERE c.risk_level = 'HIGH' 
           ORDER BY c.id DESC LIMIT 5"""
    ).fetchall()]

    # 오늘/금주 부재 상담사 현황
    upcoming_leaves = [dict(r) for r in conn.execute(
        """SELECT l.*, c.name as counselor_name, c.title as counselor_title 
           FROM leave_requests l 
           JOIN counselors c ON l.counselor_id = c.id 
           WHERE l.status = 'APPROVED' AND l.end_date >= ? 
           ORDER BY l.start_date ASC LIMIT 5""", (today_str,)
    ).fetchall()]

    conn.close()
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "active_menu": "dashboard",
            "user": user,
            "all_users": all_users,
            "stats": {
                "today_calls": today_calls,
                "total_calls": total_calls,
                "high_risk_count": high_risk_count,
                "pending_leaves": pending_leaves
            },
            "recent_high_risk": recent_high_risk,
            "upcoming_leaves": upcoming_leaves
        }
    )

# 1. 전화 상담기록 화면
@app.get("/calls", response_class=HTMLResponse)
async def call_logs_page(request: Request, search: Optional[str] = None, risk: Optional[str] = None, status_filter: Optional[str] = None):
    user = get_current_counselor(request)
    all_users = get_all_active_counselors()
    conn = get_db_connection()

    query = """
        SELECT c.*, cs.name as counselor_name, cs.title as counselor_title
        FROM call_logs c
        LEFT JOIN counselors cs ON c.counselor_id = cs.id
        WHERE 1=1
    """
    params = []

    if search:
        query += " AND (c.client_name LIKE ? OR c.main_issues LIKE ? OR c.counseling_content LIKE ? OR c.client_phone LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term, term])
    
    if risk and risk != "ALL":
        query += " AND c.risk_level = ?"
        params.append(risk)

    if status_filter and status_filter != "ALL":
        query += " AND c.status = ?"
        params.append(status_filter)

    query += " ORDER BY c.id DESC"
    calls = [dict(r) for r in conn.execute(query, params).fetchall()]

    # 통계 요약
    total_count = len(calls)
    high_risk_count = sum(1 for c in calls if c['risk_level'] == 'HIGH')
    in_progress_count = sum(1 for c in calls if c['status'] == 'IN_PROGRESS')
    completed_count = sum(1 for c in calls if c['status'] == 'COMPLETED')

    conn.close()
    return templates.TemplateResponse(
        request=request,
        name="call_logs.html",
        context={
            "active_menu": "calls",
            "user": user,
            "all_users": all_users,
            "calls": calls,
            "search": search or "",
            "risk": risk or "ALL",
            "status_filter": status_filter or "ALL",
            "summary": {
                "total": total_count,
                "high_risk": high_risk_count,
                "in_progress": in_progress_count,
                "completed": completed_count
            }
        }
    )

# 2. 휴가 신청 화면
@app.get("/leaves", response_class=HTMLResponse)
async def leaves_page(request: Request):
    user = get_current_counselor(request)
    all_users = get_all_active_counselors()
    conn = get_db_connection()

    # 모든 휴가 신청 내역
    leave_requests = [dict(r) for r in conn.execute("""
        SELECT l.*, 
               c.name as counselor_name, c.title as counselor_title, c.role as counselor_role,
               d.name as deputy_name,
               a.name as approver_name
        FROM leave_requests l
        JOIN counselors c ON l.counselor_id = c.id
        LEFT JOIN counselors d ON l.deputy_counselor_id = d.id
        LEFT JOIN counselors a ON l.approver_id = a.id
        ORDER BY l.id DESC
    """).fetchall()]

    # 최신 상담사 연차 현황 새로고침
    refreshed_user = None
    if user:
        refreshed_user = dict(conn.execute("SELECT * FROM counselors WHERE id = ?", (user['id'],)).fetchone())

    conn.close()
    return templates.TemplateResponse(
        request=request,
        name="leaves.html",
        context={
            "active_menu": "leaves",
            "user": refreshed_user or user,
            "all_users": all_users,
            "leave_requests": leave_requests
        }
    )

# 3. 상담사 관리 화면
@app.get("/counselors", response_class=HTMLResponse)
async def counselors_page(request: Request):
    user = get_current_counselor(request)
    all_users = get_all_active_counselors()
    conn = get_db_connection()

    counselors_list = []
    rows = conn.execute("""
        SELECT c.*,
               (SELECT COUNT(*) FROM call_logs cl WHERE cl.counselor_id = c.id) as assigned_calls_count,
               (SELECT COUNT(*) FROM leave_requests lr WHERE lr.counselor_id = c.id AND lr.status = 'PENDING') as pending_leave_count
        FROM counselors c
        ORDER BY CASE c.role 
            WHEN 'DIRECTOR' THEN 1 
            WHEN 'SENIOR' THEN 2 
            WHEN 'COUNSELOR' THEN 3 
            ELSE 4 END, c.id ASC
    """).fetchall()

    for r in rows:
        counselors_list.append(dict(r))

    conn.close()
    return templates.TemplateResponse(
        request=request,
        name="counselors.html",
        context={
            "active_menu": "counselors",
            "user": user,
            "all_users": all_users,
            "counselors": counselors_list
        }
    )

# 4. 업무일지 화면
@app.get("/worklogs", response_class=HTMLResponse)
async def work_logs_page(request: Request, selected_date: Optional[str] = None):
    user = get_current_counselor(request)
    all_users = get_all_active_counselors()
    conn = get_db_connection()

    today_str = date.today().strftime("%Y-%m-%d")
    target_date = selected_date or today_str

    # 업무일지 목록 (최근 30일)
    logs_list = [dict(r) for r in conn.execute("""
        SELECT w.*, c.name as counselor_name, c.title as counselor_title,
               a.name as approver_name
        FROM work_logs w
        JOIN counselors c ON w.counselor_id = c.id
        LEFT JOIN counselors a ON w.approver_id = a.id
        ORDER BY w.log_date DESC LIMIT 30
    """).fetchall()]

    # 선택된 일자의 업무일지 조회
    current_log = conn.execute("""
        SELECT w.*, c.name as counselor_name, c.title as counselor_title,
               a.name as approver_name
        FROM work_logs w
        JOIN counselors c ON w.counselor_id = c.id
        LEFT JOIN counselors a ON w.approver_id = a.id
        WHERE w.log_date = ?
    """, (target_date,)).fetchone()

    # 해당 날짜의 실제 상담 통계 자동 집계
    day_calls = conn.execute("""
        SELECT COUNT(*) as total_calls,
               SUM(CASE WHEN risk_level = 'HIGH' THEN 1 ELSE 0 END) as high_risk_calls
        FROM call_logs
        WHERE call_date LIKE ?
    """, (f"{target_date}%",)).fetchone()

    day_calls_list = [dict(r) for r in conn.execute("""
        SELECT c.*, cs.name as counselor_name
        FROM call_logs c
        LEFT JOIN counselors cs ON c.counselor_id = cs.id
        WHERE c.call_date LIKE ?
        ORDER BY c.id ASC
    """, (f"{target_date}%",)).fetchall()]

    conn.close()
    return templates.TemplateResponse(
        request=request,
        name="work_logs.html",
        context={
            "active_menu": "worklogs",
            "user": user,
            "all_users": all_users,
            "target_date": target_date,
            "today_str": today_str,
            "logs_list": logs_list,
            "current_log": dict(current_log) if current_log else None,
            "day_stats": {
                "total_calls": day_calls['total_calls'] or 0,
                "high_risk_calls": day_calls['high_risk_calls'] or 0
            },
            "day_calls": day_calls_list
        }
    )

# 5. 마이페이지 화면
@app.get("/mypage", response_class=HTMLResponse)
async def mypage(request: Request):
    user = get_current_counselor(request)
    all_users = get_all_active_counselors()
    conn = get_db_connection()

    if not user:
        conn.close()
        return RedirectResponse(url="/")

    # 내 프로필 정보 최신화
    profile = dict(conn.execute("SELECT * FROM counselors WHERE id = ?", (user['id'],)).fetchone())

    # 내 담당 상담 목록 (최근 10건)
    my_calls = [dict(r) for r in conn.execute("""
        SELECT * FROM call_logs WHERE counselor_id = ? ORDER BY id DESC LIMIT 10
    """, (user['id'],)).fetchall()]

    # 내 휴가 신청 내역
    my_leaves = [dict(r) for r in conn.execute("""
        SELECT l.*, d.name as deputy_name, a.name as approver_name
        FROM leave_requests l
        LEFT JOIN counselors d ON l.deputy_counselor_id = d.id
        LEFT JOIN counselors a ON l.approver_id = a.id
        WHERE l.counselor_id = ?
        ORDER BY l.id DESC
    """, (user['id'],)).fetchall()]

    # 내가 작성한 업무일지
    my_worklogs = [dict(r) for r in conn.execute("""
        SELECT * FROM work_logs WHERE counselor_id = ? ORDER BY log_date DESC LIMIT 10
    """, (user['id'],)).fetchall()]

    # 내 통계
    my_stats = {
        "assigned_calls": conn.execute("SELECT COUNT(*) FROM call_logs WHERE counselor_id = ?", (user['id'],)).fetchone()[0],
        "completed_calls": conn.execute("SELECT COUNT(*) FROM call_logs WHERE counselor_id = ? AND status = 'COMPLETED'", (user['id'],)).fetchone()[0],
        "worklog_count": conn.execute("SELECT COUNT(*) FROM work_logs WHERE counselor_id = ?", (user['id'],)).fetchone()[0],
        "remaining_leave": profile['annual_leave_total'] - profile['annual_leave_used']
    }

    conn.close()
    return templates.TemplateResponse(
        request=request,
        name="mypage.html",
        context={
            "active_menu": "mypage",
            "user": profile,
            "all_users": all_users,
            "profile": profile,
            "my_calls": my_calls,
            "my_leaves": my_leaves,
            "my_worklogs": my_worklogs,
            "my_stats": my_stats
        }
    )


# ----------------- REST API 엔드포인트 -----------------

# 빠른 상담사 전환 (데모/테스트 편의성)
@app.post("/api/switch-user/{counselor_id}")
async def switch_user(counselor_id: int, response: Response):
    conn = get_db_connection()
    counselor = conn.execute("SELECT * FROM counselors WHERE id = ? AND is_active = 1", (counselor_id,)).fetchone()
    conn.close()
    if not counselor:
        raise HTTPException(status_code=404, detail="상담사를 찾을 수 없습니다.")
    
    response = JSONResponse({"success": True, "message": f"{counselor['name']} 계정으로 전환되었습니다."})
    response.set_cookie(key="current_counselor_id", value=str(counselor_id), max_age=86400 * 7, httponly=False)
    return response

# --- 1. 전화 상담기록 API ---

@app.get("/api/calls/{call_id}")
async def get_call_detail(call_id: int):
    conn = get_db_connection()
    call = conn.execute("""
        SELECT c.*, cs.name as counselor_name, cs.title as counselor_title
        FROM call_logs c
        LEFT JOIN counselors cs ON c.counselor_id = cs.id
        WHERE c.id = ?
    """, (call_id,)).fetchone()
    conn.close()
    if not call:
        raise HTTPException(status_code=404, detail="상담 기록을 찾을 수 없습니다.")
    return dict(call)

@app.post("/api/calls")
async def create_call_log(data: models.CallLogCreate, request: Request):
    user = get_current_counselor(request)
    counselor_id = data.counselor_id or (user['id'] if user else 1)
    
    call_date = data.call_date or datetime.now().strftime("%Y-%m-%d %H:%M")
    violence_str = ", ".join(data.violence_types) if data.violence_types else "기타"
    actions_str = ", ".join(data.action_types) if data.action_types else "일반상담"

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO call_logs (
            call_date, client_name, is_anonymous, client_gender, client_age_group,
            client_phone, client_region, violence_types, perpetrator_relation,
            risk_level, incident_history, main_issues, counseling_content,
            action_types, status, counselor_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        call_date, data.client_name, data.is_anonymous, data.client_gender, data.client_age_group,
        data.client_phone, data.client_region, violence_str, data.perpetrator_relation,
        data.risk_level, data.incident_history, data.main_issues, data.counseling_content,
        actions_str, data.status, counselor_id
    ))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return {"success": True, "id": new_id, "message": "전화 상담 기록이 성공적으로 등록되었습니다."}

@app.put("/api/calls/{call_id}")
async def update_call_log(call_id: int, data: models.CallLogUpdate):
    conn = get_db_connection()
    existing = conn.execute("SELECT * FROM call_logs WHERE id = ?", (call_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다.")

    violence_str = ", ".join(data.violence_types) if data.violence_types is not None else existing['violence_types']
    actions_str = ", ".join(data.action_types) if data.action_types is not None else existing['action_types']

    conn.execute("""
        UPDATE call_logs SET
            call_date = COALESCE(?, call_date),
            client_name = COALESCE(?, client_name),
            is_anonymous = COALESCE(?, is_anonymous),
            client_gender = COALESCE(?, client_gender),
            client_age_group = COALESCE(?, client_age_group),
            client_phone = COALESCE(?, client_phone),
            client_region = COALESCE(?, client_region),
            violence_types = ?,
            perpetrator_relation = COALESCE(?, perpetrator_relation),
            risk_level = COALESCE(?, risk_level),
            incident_history = COALESCE(?, incident_history),
            main_issues = COALESCE(?, main_issues),
            counseling_content = COALESCE(?, counseling_content),
            action_types = ?,
            status = COALESCE(?, status),
            counselor_id = COALESCE(?, counselor_id),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (
        data.call_date, data.client_name, data.is_anonymous, data.client_gender, data.client_age_group,
        data.client_phone, data.client_region, violence_str, data.perpetrator_relation,
        data.risk_level, data.incident_history, data.main_issues, data.counseling_content,
        actions_str, data.status, data.counselor_id, call_id
    ))
    conn.commit()
    conn.close()
    return {"success": True, "message": "상담 기록이 수정되었습니다."}

@app.delete("/api/calls/{call_id}")
async def delete_call_log(call_id: int):
    conn = get_db_connection()
    conn.execute("DELETE FROM call_logs WHERE id = ?", (call_id,))
    conn.commit()
    conn.close()
    return {"success": True, "message": "상담 기록이 삭제되었습니다."}

@app.get("/api/calls/export/csv")
async def export_calls_csv():
    conn = get_db_connection()
    calls = conn.execute("""
        SELECT c.id, c.call_date, c.client_name, c.is_anonymous, c.client_gender, c.client_age_group,
               c.client_region, c.violence_types, c.perpetrator_relation, c.risk_level,
               c.status, cs.name as counselor_name
        FROM call_logs c
        LEFT JOIN counselors cs ON c.counselor_id = cs.id
        ORDER BY c.id DESC
    """).fetchall()
    conn.close()

    output = io.StringIO()
    # UTF-8 BOM 추가 (Excel에서 한글 깨짐 방지)
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(["접수번호", "상담일시", "내담자명", "익명여부", "성별", "연령대", "거주지역", "폭력유형", "가해자관계", "위험등급", "진행상태", "담당상담사"])
    
    for c in calls:
        writer.writerow([
            c["id"], c["call_date"], c["client_name"],
            "익명" if c["is_anonymous"] else "실명",
            c["client_gender"], c["client_age_group"] or "",
            c["client_region"] or "", c["violence_types"], c["perpetrator_relation"],
            c["risk_level"], c["status"], c["counselor_name"] or ""
        ])
    
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=counseling_call_logs.csv"}
    )

# --- 2. 휴가 신청 API ---

@app.post("/api/leaves")
async def create_leave_request(data: models.LeaveRequestCreate, request: Request):
    user = get_current_counselor(request)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    conn = get_db_connection()
    # 잔여 연차 검사 (연차/반차일 경우)
    if "연차" in data.leave_type or "반차" in data.leave_type:
        counselor = conn.execute("SELECT * FROM counselors WHERE id = ?", (user['id'],)).fetchone()
        remaining = counselor['annual_leave_total'] - counselor['annual_leave_used']
        if remaining < data.days_count:
            conn.close()
            raise HTTPException(status_code=400, detail=f"잔여 연차({remaining}일)가 신청 일수({data.days_count}일)보다 부족합니다.")

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO leave_requests (
            counselor_id, leave_type, start_date, end_date, days_count, reason, deputy_counselor_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        user['id'], data.leave_type, data.start_date, data.end_date, data.days_count, data.reason, data.deputy_counselor_id
    ))
    conn.commit()
    conn.close()
    return {"success": True, "message": "휴가 신청이 정상적으로 접수되었습니다."}

@app.post("/api/leaves/{leave_id}/process")
async def process_leave_request(leave_id: int, data: models.LeaveApprovalUpdate, request: Request):
    user = get_current_counselor(request)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    conn = get_db_connection()
    leave = conn.execute("SELECT * FROM leave_requests WHERE id = ?", (leave_id,)).fetchone()
    if not leave:
        conn.close()
        raise HTTPException(status_code=404, detail="휴가 신청 내역을 찾을 수 없습니다.")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # 승인 처리 및 잔여 연차 차감 로직
    if data.status == "APPROVED" and leave['status'] != "APPROVED":
        if "연차" in leave['leave_type'] or "반차" in leave['leave_type']:
            conn.execute("""
                UPDATE counselors 
                SET annual_leave_used = annual_leave_used + ? 
                WHERE id = ?
            """, (leave['days_count'], leave['counselor_id']))

    # 이전에 승인되었다가 반려로 바뀐 경우 연차 복원
    elif data.status == "REJECTED" and leave['status'] == "APPROVED":
        if "연차" in leave['leave_type'] or "반차" in leave['leave_type']:
            conn.execute("""
                UPDATE counselors 
                SET annual_leave_used = MAX(0, annual_leave_used - ?) 
                WHERE id = ?
            """, (leave['days_count'], leave['counselor_id']))

    conn.execute("""
        UPDATE leave_requests 
        SET status = ?, approver_id = ?, reject_reason = ?, approved_at = ?
        WHERE id = ?
    """, (data.status, user['id'], data.reject_reason, now_str, leave_id))
    
    conn.commit()
    conn.close()
    return {"success": True, "message": f"휴가 신청이 {'승인' if data.status == 'APPROVED' else '반려'}되었습니다."}

@app.delete("/api/leaves/{leave_id}")
async def cancel_leave_request(leave_id: int, request: Request):
    user = get_current_counselor(request)
    conn = get_db_connection()
    leave = conn.execute("SELECT * FROM leave_requests WHERE id = ?", (leave_id,)).fetchone()
    if not leave:
        conn.close()
        raise HTTPException(status_code=404, detail="휴가 신청을 찾을 수 없습니다.")

    # 승인된 상태였던 경우 연차 복원
    if leave['status'] == "APPROVED" and ("연차" in leave['leave_type'] or "반차" in leave['leave_type']):
        conn.execute("""
            UPDATE counselors 
            SET annual_leave_used = MAX(0, annual_leave_used - ?) 
            WHERE id = ?
        """, (leave['days_count'], leave['counselor_id']))

    conn.execute("DELETE FROM leave_requests WHERE id = ?", (leave_id,))
    conn.commit()
    conn.close()
    return {"success": True, "message": "휴가 신청이 취소/삭제되었습니다."}

# --- 3. 상담사 관리 API ---

@app.post("/api/counselors")
async def create_counselor(data: models.CounselorCreate):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO counselors (username, password, name, role, title, phone, email, specialties, annual_leave_total)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.username, data.password, data.name, data.role, data.title,
            data.phone, data.email, data.specialties, data.annual_leave_total
        ))
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()
        return {"success": True, "id": new_id, "message": "신규 상담사가 등록되었습니다."}
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail="아이디 중복 또는 등록 실패: " + str(e))

@app.put("/api/counselors/{counselor_id}")
async def update_counselor(counselor_id: int, data: models.CounselorUpdate):
    conn = get_db_connection()
    counselor = conn.execute("SELECT * FROM counselors WHERE id = ?", (counselor_id,)).fetchone()
    if not counselor:
        conn.close()
        raise HTTPException(status_code=404, detail="상담사를 찾을 수 없습니다.")

    conn.execute("""
        UPDATE counselors SET
            name = COALESCE(?, name),
            title = COALESCE(?, title),
            phone = COALESCE(?, phone),
            email = COALESCE(?, email),
            specialties = COALESCE(?, specialties),
            password = COALESCE(?, password),
            role = COALESCE(?, role),
            annual_leave_total = COALESCE(?, annual_leave_total),
            is_active = COALESCE(?, is_active)
        WHERE id = ?
    """, (
        data.name, data.title, data.phone, data.email, data.specialties,
        data.password, data.role, data.annual_leave_total, data.is_active, counselor_id
    ))
    conn.commit()
    conn.close()
    return {"success": True, "message": "상담사 정보가 수정되었습니다."}

# --- 4. 업무일지 API ---

@app.post("/api/worklogs")
async def save_work_log(data: models.WorkLogCreate, request: Request):
    user = get_current_counselor(request)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    conn = get_db_connection()
    # 해당 날짜의 실제 상담 통계 조회
    stats = conn.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN risk_level = 'HIGH' THEN 1 ELSE 0 END) as high_risk
        FROM call_logs WHERE call_date LIKE ?
    """, (f"{data.log_date}%",)).fetchone()

    total_count = stats['total'] or 0
    high_risk_count = stats['high_risk'] or 0

    existing = conn.execute("SELECT * FROM work_logs WHERE log_date = ?", (data.log_date,)).fetchone()
    if existing:
        conn.execute("""
            UPDATE work_logs SET
                counselor_id = ?,
                total_calls_count = ?,
                high_risk_calls_count = ?,
                counseling_summary = ?,
                admin_tasks = ?,
                crisis_cases = ?,
                tomorrow_plan = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE log_date = ?
        """, (
            user['id'], total_count, high_risk_count,
            data.counseling_summary, data.admin_tasks, data.crisis_cases, data.tomorrow_plan,
            data.log_date
        ))
    else:
        conn.execute("""
            INSERT INTO work_logs (
                log_date, counselor_id, total_calls_count, high_risk_calls_count,
                counseling_summary, admin_tasks, crisis_cases, tomorrow_plan
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.log_date, user['id'], total_count, high_risk_count,
            data.counseling_summary, data.admin_tasks, data.crisis_cases, data.tomorrow_plan
        ))

    conn.commit()
    conn.close()
    return {"success": True, "message": f"{data.log_date} 업무일지가 저장되었습니다."}

@app.post("/api/worklogs/{log_date}/feedback")
async def save_work_log_feedback(log_date: str, data: models.WorkLogFeedbackUpdate, request: Request):
    user = get_current_counselor(request)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    conn = get_db_connection()
    conn.execute("""
        UPDATE work_logs SET
            feedback = ?,
            approver_id = ?,
            is_confirmed = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE log_date = ?
    """, (data.feedback, user['id'], data.is_confirmed, log_date))
    conn.commit()
    conn.close()
    return {"success": True, "message": "일지 검토 및 확인 피드백이 등록되었습니다."}

# --- 5. 대시보드 통계 API ---
@app.get("/api/stats/dashboard")
async def get_dashboard_chart_data():
    conn = get_db_connection()
    
    # 폭력 유형별 통계
    calls = conn.execute("SELECT violence_types FROM call_logs").fetchall()
    v_counts = {"신체적 폭력": 0, "정서/언어적 폭력": 0, "경제적 폭력": 0, "성적 폭력": 0, "통제/방임": 0}
    for row in calls:
        v_str = row['violence_types'] or ""
        for k in v_counts.keys():
            if k in v_str:
                v_counts[k] += 1

    # 위험도 비율
    risk_rows = conn.execute("SELECT risk_level, COUNT(*) as cnt FROM call_logs GROUP BY risk_level").fetchall()
    risk_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for r in risk_rows:
        risk_counts[r['risk_level']] = r['cnt']

    conn.close()
    return {
        "violence_stats": v_counts,
        "risk_stats": risk_counts
    }

# --- 6. Typebot 연동 Webhook API ---
@app.post("/api/webhook/typebot")
async def receive_typebot_submission(payload: dict):
    """
    Typebot 챗봇에서 사용자가 상담 접수를 완료했을 때 전송되는 웹훅 수신
    """
    try:
        client_name = payload.get("client_name") or payload.get("name") or "챗봇접수 내담자"
        is_anon = 1 if payload.get("is_anonymous") in [True, 1, "true", "True", "익명", "on"] else 0
        gender = payload.get("gender") or payload.get("client_gender") or "여성"
        age_group = payload.get("age_group") or payload.get("client_age_group") or "미상"
        phone = payload.get("phone") or payload.get("client_phone") or "미입력"
        region = payload.get("region") or payload.get("client_region") or "지역미상"
        
        v_types = payload.get("violence_types") or ["일반/기타"]
        if isinstance(v_types, list):
            v_types_str = ", ".join(v_types)
        else:
            v_types_str = str(v_types)

        relation = payload.get("perpetrator_relation") or payload.get("relation") or "배우자/교제상대"
        risk = str(payload.get("risk_level", "MEDIUM")).upper()
        if risk not in ["HIGH", "MEDIUM", "LOW"]:
            risk = "MEDIUM"

        issues = payload.get("main_issues") or payload.get("issue") or "Typebot 온라인 챗봇 접수 건"
        content = payload.get("counseling_content") or payload.get("message") or json.dumps(payload, ensure_ascii=False, indent=2)
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO call_logs (
                call_date, client_name, is_anonymous, client_gender, client_age_group,
                client_phone, client_region, violence_types, perpetrator_relation,
                risk_level, incident_history, main_issues, counseling_content,
                action_types, status, counselor_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now_str, client_name, is_anon, gender, age_group,
            phone, region, v_types_str, relation,
            risk, "온라인 챗봇(Typebot)을 통한 비대면 접수", issues,
            f"[Typebot 챗봇 자동 접수 내역]\n{content}",
            "온라인접수, 상담사확인대기", "RECEIVED", 1
        ))
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()

        return {"success": True, "id": new_id, "message": "Typebot 상담 접수가 성공적으로 등록되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook 처리 실패: {str(e)}")

# --- 7. 전화 통화 녹취록(Tyro/Tiro) AI 자동 분석 및 일지 생성 API ---
class TranscriptAnalyzeRequest(models.BaseModel):
    transcript: str
    counselor_id: Optional[int] = None

@app.post("/api/calls/analyze-transcript")
async def analyze_call_transcript(data: TranscriptAnalyzeRequest):
    """
    통화 녹음/전사 텍스트(Tiro/Tyro, STT)를 분석하여
    폭력 유형, 위험도, 가해자 관계, 주요 호소 및 조치 사항을 자동 추출
    """
    text = data.transcript.strip()
    if not text:
        raise HTTPException(status_code=400, detail="통화 내용(녹취록)이 비어 있습니다.")

    # 1. 가해자 관계 자동 감지
    relation = "배우자"
    if any(k in text for k in ["남자친구", "남친", "애인", "교제", "데이트", "이별"]):
        relation = "교제상대"
    elif any(k in text for k in ["전남편", "전처", "이혼한", "별거"]):
        relation = "전배우자"
    elif any(k in text for k in ["동거", "사실혼"]):
        relation = "사실혼"
    elif any(k in text for k in ["아버지", "어머니", "부모", "자녀", "딸", "아들"]):
        relation = "직계가족"

    # 2. 폭력 유형 자동 태깅
    violence_types = []
    if any(k in text for k in ["때리", "맞았", "폭행", "밀치", "멱살", "흉기", "칼", "멍", "상해", "목을", "발로"]):
        violence_types.append("신체적 폭력")
    if any(k in text for k in ["욕", "폭언", "소리", "무시", "인격", "모욕", "가스라이팅", "비난"]):
        violence_types.append("정서/언어적 폭력")
    if any(k in text for k in ["생활비", "돈", "경제", "카드", "통장", "일 못하게", "빚"]):
        violence_types.append("경제적 폭력")
    if any(k in text for k in ["성관계", "강제", "추행", "성적"]):
        violence_types.append("성적 폭력")
    if any(k in text for k in ["감시", "위치추적", "스토킹", "문자 수백", "휴대폰 검사", "못 나가게", "감금"]):
        violence_types.append("통제/방임")
    if not violence_types:
        violence_types.append("정서/언어적 폭력")

    # 3. 위험도(Triage) 자동 판별
    risk_level = "LOW"
    high_keywords = ["흉기", "칼", "죽이겠다", "살려", "모텔", "도망", "피신", "기절", "응급", "병원", "목을 조", "골절"]
    medium_keywords = ["반복", "상습", "욕설", "위협", "불안", "우울", "경찰", "112", "가출"]
    
    if any(k in text for k in high_keywords):
        risk_level = "HIGH"
    elif any(k in text for k in medium_keywords) or len(violence_types) >= 2:
        risk_level = "MEDIUM"

    # 4. 권장 조치 사항
    action_types = []
    if risk_level == "HIGH" or any(k in text for k in ["쉼터", "잠잘", "피신", "갈 곳"]):
        action_types.append("긴급피난/쉼터")
    if any(k in text for k in ["경찰", "112", "신고", "신변보호", "스마트워치"]):
        action_types.append("경찰연계")
    if any(k in text for k in ["이혼", "법률", "소송", "재산", "고소"]):
        action_types.append("법률구조안내")
    if any(k in text for k in ["병원", "치료", "외상", "응급"]):
        action_types.append("의료지원")
    action_types.append("심리상담예약")

    # 5. 요약 생성
    summary_lines = [line.strip() for line in text.split("\n") if line.strip()]
    first_few = " ".join(summary_lines[:2])
    main_issues = first_few[:60] + "..." if len(first_few) > 60 else first_few

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    return {
        "success": True,
        "extracted_data": {
            "call_date": now_str,
            "client_name": "상담내담자",
            "is_anonymous": 0,
            "client_gender": "여성",
            "client_age_group": "30대",
            "perpetrator_relation": relation,
            "violence_types": violence_types,
            "risk_level": risk_level,
            "main_issues": f"[{relation} {violence_types[0]}] {main_issues}",
            "counseling_content": f"[통화 내용 기반 상담 기록 요약]\n\n■ 주요 진술 및 피해 정황:\n{text}\n\n■ 초기 위험도 평가: {risk_level}\n■ 권장 후속 개입: {', '.join(action_types)}",
            "action_types": action_types,
            "status": "IN_PROGRESS"
        }
    }


