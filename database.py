import os
import sqlite3
import json
from datetime import datetime, date, timedelta
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "counseling_center.db"

TURSO_DATABASE_URL = os.environ.get("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")

def get_clean_turso_url(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    # libsql:// 스킴은 WebSocket 400 오류를 일으킬 수 있으므로 안정적인 https:// 스킴으로 자동 변환
    if url.startswith("libsql://"):
        return "https://" + url[len("libsql://"):]
    return url

# Turso LibSQL Row 래퍼 (sqlite3.Row 호환)
class LibsqlRow:
    def __init__(self, cols, vals):
        self._cols = list(cols)
        self._vals = list(vals)
        self._d = dict(zip(cols, vals))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._vals[key]
        return self._d[key]

    def get(self, key, default=None):
        return self._d.get(key, default)

    def keys(self):
        return self._d.keys()

    def values(self):
        return self._d.values()

    def items(self):
        return self._d.items()

    def __iter__(self):
        return iter(self._d)

    def __repr__(self):
        return repr(self._d)

class LibsqlCursorWrapper:
    def __init__(self, client):
        self.client = client
        self.lastrowid = None
        self.last_res = None
        self._rows = []
        self._idx = 0

    def execute(self, sql, params=()):
        args = list(params)
        res = self.client.execute(sql, args)
        self.last_res = res
        self.lastrowid = getattr(res, "last_insert_rowid", None)
        self._rows = [LibsqlRow(res.columns, r) for r in res.rows]
        self._idx = 0
        return self

    def fetchone(self):
        if self._idx < len(self._rows):
            row = self._rows[self._idx]
            self._idx += 1
            return row
        return None

    def fetchall(self):
        rows = self._rows[self._idx:]
        self._idx = len(self._rows)
        return rows

class LibsqlConnectionWrapper:
    def __init__(self, client):
        self.client = client

    def cursor(self):
        return LibsqlCursorWrapper(self.client)

    def execute(self, sql, params=()):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        # Turso(HTTP)는 개별 요청마다 자동 커밋됩니다.
        pass

    def close(self):
        self.client.close()

def get_db_connection():
    """
    환경 변수에 TURSO_DATABASE_URL이 등록되어 있으면 Turso 클라우드 DB에 연결하고,
    등록되어 있지 않으면 로컬 SQLite 파일(counseling_center.db)에 연결합니다.
    """
    if TURSO_DATABASE_URL and TURSO_AUTH_TOKEN:
        import libsql_client
        clean_url = get_clean_turso_url(TURSO_DATABASE_URL)
        client = libsql_client.create_client_sync(
            url=clean_url,
            auth_token=TURSO_AUTH_TOKEN.strip()
        )
        return LibsqlConnectionWrapper(client)
    else:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # WAL(Write-Ahead Logging) 모드 적용: 서버 재실행/급작스런 종료 시에도 데이터 손실 방지 및 무결성 보장
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

def is_using_turso() -> bool:
    return bool(TURSO_DATABASE_URL and TURSO_AUTH_TOKEN)

def get_db_status_info() -> dict:
    if is_using_turso():
        # URL에서 호스트명만 마스킹하여 추출
        db_name = TURSO_DATABASE_URL.split("@")[-1].replace("libsql://", "").replace("https://", "")
        return {
            "type": "Turso",
            "name": f"Turso 클라우드 ({db_name})",
            "is_cloud": True,
            "badge_class": "bg-emerald-50 text-emerald-700 border-emerald-300"
        }
    else:
        return {
            "type": "SQLite",
            "name": f"로컬 영구 DB ({DB_PATH.name})",
            "is_cloud": False,
            "badge_class": "bg-slate-100 text-slate-700 border-slate-300"
        }


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. 상담사 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS counselors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'COUNSELOR',
        title TEXT NOT NULL DEFAULT '상담사',
        phone TEXT,
        email TEXT,
        specialties TEXT,
        annual_leave_total REAL DEFAULT 15.0,
        annual_leave_used REAL DEFAULT 0.0,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 2. 전화 상담기록 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS call_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        call_date TEXT NOT NULL,
        client_name TEXT NOT NULL,
        is_anonymous INTEGER DEFAULT 0,
        client_gender TEXT NOT NULL DEFAULT '여성',
        client_age_group TEXT,
        client_phone TEXT,
        client_region TEXT,
        violence_types TEXT NOT NULL,
        perpetrator_relation TEXT NOT NULL,
        risk_level TEXT NOT NULL DEFAULT 'MEDIUM',
        incident_history TEXT,
        main_issues TEXT,
        counseling_content TEXT NOT NULL,
        action_types TEXT,
        status TEXT NOT NULL DEFAULT 'IN_PROGRESS',
        counselor_id INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (counselor_id) REFERENCES counselors (id)
    )
    """)

    # 3. 휴가 신청 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS leave_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        counselor_id INTEGER NOT NULL,
        leave_type TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        days_count REAL NOT NULL,
        reason TEXT NOT NULL,
        deputy_counselor_id INTEGER,
        status TEXT NOT NULL DEFAULT 'PENDING',
        approver_id INTEGER,
        reject_reason TEXT,
        approved_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (counselor_id) REFERENCES counselors (id),
        FOREIGN KEY (deputy_counselor_id) REFERENCES counselors (id),
        FOREIGN KEY (approver_id) REFERENCES counselors (id)
    )
    """)

    # 4. 업무일지 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS work_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        log_date TEXT UNIQUE NOT NULL,
        counselor_id INTEGER NOT NULL,
        total_calls_count INTEGER DEFAULT 0,
        high_risk_calls_count INTEGER DEFAULT 0,
        counseling_summary TEXT,
        admin_tasks TEXT,
        crisis_cases TEXT,
        tomorrow_plan TEXT,
        feedback TEXT,
        approver_id INTEGER,
        is_confirmed INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (counselor_id) REFERENCES counselors (id),
        FOREIGN KEY (approver_id) REFERENCES counselors (id)
    )
    """)

    conn.commit()

    # 초기 데이터 시딩 검사
    row = cursor.execute("SELECT COUNT(*) FROM counselors").fetchone()
    if row and row[0] == 0:
        seed_data(conn)

    conn.close()

def seed_data(conn):
    cursor = conn.cursor()

    counselors_data = [
        ("director", "1234", "김지은", "DIRECTOR", "소장", "010-3456-7890", "director@counsel.kr", "위기개입,법률지원,트라우마치유", 18.0, 3.5),
        ("seoyun", "1234", "박서윤", "SENIOR", "선임상담사", "010-4567-8901", "seoyun@counsel.kr", "가정폭력상담,부부갈등,긴급쉼터연계", 15.0, 4.0),
        ("minwoo", "1234", "이민우", "COUNSELOR", "전문상담사", "010-5678-9012", "minwoo@counsel.kr", "피해자심리상담,남성상담,가족상담", 15.0, 1.5),
        ("haneul", "1234", "정하늘", "COUNSELOR", "상담사", "010-6789-0123", "haneul@counsel.kr", "교제폭력,청년상담,정서적학대", 15.0, 2.0)
    ]

    for username, pwd, name, role, title, phone, email, spec, total_leave, used_leave in counselors_data:
        cursor.execute("""
        INSERT INTO counselors (username, password, name, role, title, phone, email, specialties, annual_leave_total, annual_leave_used)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (username, pwd, name, role, title, phone, email, spec, total_leave, used_leave))

    today = date.today().strftime("%Y-%m-%d")
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    two_days_ago = (date.today() - timedelta(days=2)).strftime("%Y-%m-%d")
    three_days_ago = (date.today() - timedelta(days=3)).strftime("%Y-%m-%d")

    sample_calls = [
        (
            f"{today} 09:30", "이지혜", 0, "여성", "30대", "010-9811-2345", "서울 강서구",
            "신체적 폭력, 정서/언어적 폭력, 통제/방임", "배우자", "HIGH",
            "결혼 5년차, 음주 후 상습적 폭행(흉기 위협 1회), 최근 3개월간 격화됨. 112 신고 이력 2회(처벌불원 의사표시 후 종결됨)",
            "어젯밤 남편의 심한 폭행으로 자녀(6세)와 함께 집을 나와 인근 모텔에 머물고 있음. 극심한 불안감과 신체 통증 호소.",
            "신체적 상해 부위 확인 및 응급병원 연계 안내. 자녀와 함께 긴급히 피신할 수 있는 긴급피난처(단기쉼터) 입소 의사 타진하여 연계 절차 착수. 피해자 동의 하에 경찰 신변보호 신청 방법 및 스마트워치 지급 안내.",
            "긴급피난/쉼터, 경찰연계, 의료지원, 법률구조안내", "IN_PROGRESS", 2
        ),
        (
            f"{today} 11:15", "익명내담자", 1, "여성", "20대", "010-0000-0000", "서울 마포구",
            "정서/언어적 폭력, 통제/방임", "교제상대", "MEDIUM",
            "교제 1년 6개월, 휴대전화 불시 검사 및 위치 추적 앱 강제 설치, 친구들과의 연락 차단 등 극심한 가스라이팅",
            "이별 통보 시 직장 및 자택으로 찾아오거나 자해하겠다고 협박하여 벗어나지 못하고 있는 상태. 불면증 및 우울감 호소.",
            "가스라이팅 및 데이트폭력의 위험성 객관화 지원. 안전한 이별을 위한 대처 수칙(혼자 만나지 않기, 모든 협박 메시지 녹취 및 캡처 백업 등) 안내. 센터 내 대면 심리상담(다음 주 화요일) 1회차 예약 확정.",
            "심리상담예약, 법률구조안내", "FOLLOW_UP", 4
        ),
        (
            f"{today} 14:00", "최영숙", 0, "여성", "50대", "010-7788-3412", "경기 고양시",
            "경제적 폭력, 정서/언어적 폭력", "배우자", "LOW",
            "결혼 28년차, 남편의 일방적인 생활비 지급 중단 및 경제활동 방해, 지속적인 폭언 및 무시",
            "자녀들이 독립한 후 폭언이 더 심해졌으며 본인 명의 재산이 전혀 없어 생계에 대한 극심한 불안감 호소. 이혼 의향 있으나 법적 절차 및 재산분할 방법을 모름.",
            "가정폭력 피해자 무료 법률구조 지원(대한법률구조공단 연계) 제도 상세 안내 및 신청 구비서류 목록 문자 발송. 심리적 자존감 회복을 위한 집단상담 프로그램 안내.",
            "법률구조안내, 심리상담예약", "COMPLETED", 3
        ),
        (
            f"{yesterday} 10:20", "박민지", 0, "여성", "40대", "010-6543-1298", "서울 영등포구",
            "신체적 폭력, 경제적 폭력", "배우자", "HIGH",
            "10여 년간 가정폭력 누적, 최근 의처증 증세로 둔기 사용 폭행 발생, 경찰 출동 후 임시조치 1~3호 신청 이력 있음",
            "접근금지 가처분 기간 종료를 앞두고 가해자의 보복 우려 및 주거지 노출에 따른 극도의 공포감.",
            "가정폭력 피해자 주민등록등초본 열람제한 신청 지원 절차 안내. 법률구조공단 변호사 연계를 통한 피해자보호명령 연장 청구 지원. 관할 경찰서 피해자전담경찰관(APO) 핫라인 연결.",
            "법률구조안내, 경찰연계, 심리상담예약", "IN_PROGRESS", 2
        ),
        (
            f"{yesterday} 15:40", "김은선", 0, "여성", "30대", "010-4422-9901", "인천 부평구",
            "성적 폭력, 신체적 폭력", "사실혼", "HIGH",
            "동거 3년차, 강제적 성관계 요구 및 거부 시 목을 조르는 등의 물리적 폭행 발생",
            "외상(목 부위 찰과상) 사진 증거 확보 여부 확인 필요. 가족이나 지인에게 알리지 못해 고립된 상태.",
            "해바라기센터 연계를 통한 증거 채취 및 전문 의료·심리지원 연계. 즉각적인 안전 확보를 위해 거주지 분리 권고 및 관할 쉼터 입소 상담 접수.",
            "긴급피난/쉼터, 의료지원, 경찰연계", "IN_PROGRESS", 1
        ),
        (
            f"{two_days_ago} 13:10", "정수아", 0, "여성", "20대", "010-1234-5678", "서울 서대문구",
            "통제/방임, 정서/언어적 폭력", "교제상대", "LOW",
            "헤어진 전 남자친구의 스토킹성 전화(하루 50통 이상) 및 SNS 감시",
            "신체적 위해는 없었으나 일상생활 영위가 불가능할 정도의 정신적 고통.",
            "스토킹범죄처벌법 상 잠정조치 및 서면경고 조치 안내. 통화 내역 기록 및 통신사 번호변경, 경찰 스마트워치 대여 절차 안내.",
            "법률구조안내, 경찰연계", "COMPLETED", 4
        ),
        (
            f"{two_days_ago} 16:30", "한미래", 0, "여성", "40대", "010-3344-7788", "서울 구로구",
            "신체적 폭력, 정서/언어적 폭력, 경제적 폭력", "배우자", "MEDIUM",
            "명절 전후로 폭언 및 폭행 빈도 증가, 자녀들 앞에서 물건을 부수고 위협함",
            "자녀들에게 미칠 정서적 악영향 우려 및 이혼 결심. 상담소를 통해 안전하게 대응할 절차 문의.",
            "가정폭력 목격 아동의 아동학대(정서학대) 해당성 안내. 부모-자녀 동반 심리검사 일정 조율 및 상담소 내방 상담 예약.",
            "심리상담예약, 법률구조안내", "FOLLOW_UP", 3
        ),
        (
            f"{three_days_ago} 11:00", "송현정", 0, "여성", "30대", "010-5566-2211", "경기 부천시",
            "정서/언어적 폭력", "직계가족", "LOW",
            "성인 자녀에 대한 친정부모의 과도한 통제 및 언어폭력, 경제적 종속 강요",
            "가족 내 정서적 경계선 설정 및 독립 방안에 대한 고민 상담.",
            "원가족과의 물리적·정서적 분리 필요성 공감 및 1:1 심리상담 4회기 프로그램 연계 안내.",
            "심리상담예약", "COMPLETED", 3
        )
    ]

    for call in sample_calls:
        cursor.execute("""
        INSERT INTO call_logs (
            call_date, client_name, is_anonymous, client_gender, client_age_group, client_phone, client_region,
            violence_types, perpetrator_relation, risk_level, incident_history, main_issues,
            counseling_content, action_types, status, counselor_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, call)

    sample_leaves = [
        (2, "연차", (date.today() + timedelta(days=5)).strftime("%Y-%m-%d"), (date.today() + timedelta(days=5)).strftime("%Y-%m-%d"), 1.0, "가족 경조사 참석", 3, "PENDING", None, None, None),
        (3, "오전반차", (date.today() + timedelta(days=2)).strftime("%Y-%m-%d"), (date.today() + timedelta(days=2)).strftime("%Y-%m-%d"), 0.5, "병원 정기 검진", 4, "APPROVED", 1, None, today),
        (4, "연차", (date.today() + timedelta(days=10)).strftime("%Y-%m-%d"), (date.today() + timedelta(days=12)).strftime("%Y-%m-%d"), 3.0, "하반기 재충전 휴가", 2, "PENDING", None, None, None)
    ]

    for req in sample_leaves:
        cursor.execute("""
        INSERT INTO leave_requests (
            counselor_id, leave_type, start_date, end_date, days_count, reason,
            deputy_counselor_id, status, approver_id, reject_reason, approved_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, req)

    sample_worklogs = [
        (
            yesterday, 2, 4, 2,
            "1. 고위험 피해자 박민지 내담자 법률구조공단 연계 및 보호명령 연장 청구 조력\n2. 신규 전화상담 3건 진행 (교제폭력 2건, 사실혼 폭력 1건)\n3. 쉼터 입소 중인 내담자 자녀 학업 지원 현황 유선 모니터링",
            "1. 관할 경찰서(APO) 협의체 월간 간담회 안건 작성\n2. 9월 상담통계 월례보고서 1차 취합\n3. 센터 상담실 방역 및 시설 점검",
            "[위기대응] 인천 부평구 김은선 내담자 해바라기센터 응급의료 지원 및 쉼터 긴급 입소 연계 진행 완료. 안전상태 지속 점검 필요.",
            "1. 박민지 내담자 APO 미팅 동행 (오전 10시)\n2. 주간 사례회의(팀 전체) 안건 발표\n3. 신규 인턴 상담사 오리엔테이션 지원",
            "위기대응 긴급 연계 신속하게 잘 처리되었습니다. 내일 APO 미팅 결과 공유 부탁드립니다.",
            1, 1
        ),
        (
            today, 2, 3, 1,
            "1. 서울 강서구 이지혜 내담자 긴급 쉼터 연계 진행 중 (자녀 동반)\n2. 익명 내담자 가스라이팅 및 이별안전수칙 상담 진행\n3. 최영숙 내담자 무료법률구조 서류 안내",
            "1. 주간 상담 통계 업데이트\n2. 외부 후원 물품 수령 및 정리\n3. 상담원 소진 예방 프로그램 일정 공지",
            "[긴급] 이지혜 내담자 남편 흉기 위협 건 관련, 관할 경찰서 신변보호 신청 접수 동행 안내 중. 모텔 위치 보안 철저 유지 당부.",
            "1. 이지혜 내담자 쉼터 최종 입소 확인 및 후속 심리치료 연계\n2. 최영숙 내담자 서류 접수 여부 확인 전화\n3. 휴가자 업무 대행",
            None, None, 0
        )
    ]

    for log in sample_worklogs:
        cursor.execute("""
        INSERT INTO work_logs (
            log_date, counselor_id, total_calls_count, high_risk_calls_count,
            counseling_summary, admin_tasks, crisis_cases, tomorrow_plan,
            feedback, approver_id, is_confirmed
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, log)

    conn.commit()

if __name__ == "__main__":
    init_db()
    db_type = "Turso Cloud DB" if is_using_turso() else "Local SQLite"
    print(f"Database initialized successfully ({db_type}).")
