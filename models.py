from pydantic import BaseModel, Field
from typing import Optional, List

class CounselorLogin(BaseModel):
    username: str
    password: str

class CounselorCreate(BaseModel):
    username: str
    password: str = "1234"
    name: str
    role: str = "COUNSELOR"
    title: str = "상담사"
    phone: Optional[str] = None
    email: Optional[str] = None
    specialties: Optional[str] = None
    annual_leave_total: float = 15.0

class CounselorUpdate(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    specialties: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    annual_leave_total: Optional[float] = None
    is_active: Optional[int] = None

class CallLogCreate(BaseModel):
    call_date: Optional[str] = None
    client_name: str
    is_anonymous: int = 0
    client_gender: str = "여성"
    client_age_group: Optional[str] = "30대"
    client_phone: Optional[str] = None
    client_region: Optional[str] = None
    violence_types: List[str] = []
    perpetrator_relation: str = "배우자"
    risk_level: str = "MEDIUM"
    incident_history: Optional[str] = None
    main_issues: Optional[str] = None
    counseling_content: str
    action_types: List[str] = []
    status: str = "IN_PROGRESS"
    counselor_id: Optional[int] = None

class CallLogUpdate(BaseModel):
    call_date: Optional[str] = None
    client_name: Optional[str] = None
    is_anonymous: Optional[int] = None
    client_gender: Optional[str] = None
    client_age_group: Optional[str] = None
    client_phone: Optional[str] = None
    client_region: Optional[str] = None
    violence_types: Optional[List[str]] = None
    perpetrator_relation: Optional[str] = None
    risk_level: Optional[str] = None
    incident_history: Optional[str] = None
    main_issues: Optional[str] = None
    counseling_content: Optional[str] = None
    action_types: Optional[List[str]] = None
    status: Optional[str] = None
    counselor_id: Optional[int] = None

class LeaveRequestCreate(BaseModel):
    leave_type: str
    start_date: str
    end_date: str
    days_count: float = 1.0
    reason: str
    deputy_counselor_id: Optional[int] = None

class LeaveApprovalUpdate(BaseModel):
    status: str  # APPROVED, REJECTED
    reject_reason: Optional[str] = None

class WorkLogCreate(BaseModel):
    log_date: str
    counseling_summary: Optional[str] = None
    admin_tasks: Optional[str] = None
    crisis_cases: Optional[str] = None
    tomorrow_plan: Optional[str] = None

class WorkLogFeedbackUpdate(BaseModel):
    feedback: str
    is_confirmed: int = 1
