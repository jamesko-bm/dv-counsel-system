"""
로컬 SQLite DB(counseling_center.db) 데이터를 Turso 클라우드 데이터베이스로 복사/마이그레이션하는 스크립트.
사용법:
1. .env 파일에 TURSO_DATABASE_URL과 TURSO_AUTH_TOKEN을 입력합니다.
2. python migrate_to_turso.py 를 실행합니다.
"""
import os
import sqlite3
from pathlib import Path
from dotenv import load_dotenv
import libsql_client

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
LOCAL_DB_PATH = BASE_DIR / "counseling_center.db"

TURSO_URL = os.environ.get("TURSO_DATABASE_URL")
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")

def migrate():
    if not TURSO_URL or not TURSO_TOKEN:
        print("[오류] .env 파일에 TURSO_DATABASE_URL과 TURSO_AUTH_TOKEN을 먼저 설정해주세요.")
        print("예시: .env.example 파일을 복사하여 .env 파일을 만들고 토큰을 입력하세요.")
        return

    TURSO_URL_CLEAN = TURSO_URL.strip()
    if TURSO_URL_CLEAN.startswith("libsql://"):
        TURSO_URL_CLEAN = "https://" + TURSO_URL_CLEAN[len("libsql://"):]

    print(f">>> Turso 데이터베이스 연결 중: {TURSO_URL_CLEAN}")
    turso = libsql_client.create_client_sync(TURSO_URL_CLEAN, auth_token=TURSO_TOKEN.strip())

    # 1. 스키마 초기화
    print(">>> 1. Turso 테이블 스키마 생성 중...")
    schema_queries = [
        """
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
        """,
        """
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
        """,
        """
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
        """,
        """
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
        """
    ]

    for q in schema_queries:
        turso.execute(q)

    # 2. 로컬 SQLite 데이터 복사
    if LOCAL_DB_PATH.exists():
        print(">>> 2. 로컬 SQLite 데이터 복사 중...")
        local_conn = sqlite3.connect(LOCAL_DB_PATH)
        local_conn.row_factory = sqlite3.Row
        
        tables = ["counselors", "call_logs", "leave_requests", "work_logs"]
        for table in tables:
            rows = local_conn.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                continue
            cols = rows[0].keys()
            cols_str = ", ".join(cols)
            placeholders = ", ".join(["?"] * len(cols))
            
            # 기존 Turso 데이터 확인 후 없을 때만 삽입
            count = turso.execute(f"SELECT COUNT(*) FROM {table}").rows[0][0]
            if count == 0:
                print(f"  - {table} 테이블 데이터 {len(rows)}건 마이그레이션 중...")
                for row in rows:
                    turso.execute(
                        f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders})",
                        [row[col] for col in cols]
                    )
            else:
                print(f"  - {table} 테이블에 이미 {count}건의 데이터가 존재하여 건너뜁니다.")
        
        local_conn.close()
    
    turso.close()
    print(">>> [완료] Turso 데이터베이스 마이그레이션이 성공적으로 완료되었습니다!")

if __name__ == "__main__":
    migrate()
