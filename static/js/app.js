// 공통 JavaScript 라이브러리 및 유틸리티

// 토스트 메시지 출력
function showToast(message, type = 'success') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast-msg ${type === 'success' ? 'bg-emerald-600 text-white' : type === 'error' ? 'bg-rose-600 text-white' : 'bg-slate-800 text-white'}`;
    toast.innerHTML = `
        <div class="flex items-center gap-2">
            <span>${type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ'}</span>
            <span>${message}</span>
        </div>
        <button onclick="this.parentElement.remove()" class="ml-3 text-white/80 hover:text-white font-bold">&times;</button>
    `;

    container.appendChild(toast);
    setTimeout(() => toast.classList.add('show'), 10);

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

// 모달 제어
function openModal(id) {
    const el = document.getElementById(id);
    if (el) {
        el.classList.remove('hidden');
        document.body.classList.add('overflow-hidden');
    }
}

function closeModal(id) {
    const el = document.getElementById(id);
    if (el) {
        el.classList.add('hidden');
        document.body.classList.remove('overflow-hidden');
    }
}

// 상담사 빠른 전환 (데모/테스트)
async function switchCounselor(counselorId) {
    try {
        const res = await fetch(`/api/switch-user/${counselorId}`, { method: 'POST' });
        const data = await res.json();
        if (data.success) {
            showToast(data.message);
            setTimeout(() => window.location.reload(), 300);
        } else {
            showToast(data.detail || '상담사 전환에 실패했습니다.', 'error');
        }
    } catch (e) {
        console.error(e);
        showToast('통신 오류가 발생했습니다.', 'error');
    }
}

// 1. 전화 상담기록 관련 함수
async function submitCallLog(event) {
    event.preventDefault();
    const form = event.target;
    const formData = new FormData(form);

    const violenceTypes = [];
    form.querySelectorAll("input[name='violence_types']:checked").forEach(cb => {
        violenceTypes.push(cb.value);
    });

    const actionTypes = [];
    form.querySelectorAll("input[name='action_types']:checked").forEach(cb => {
        actionTypes.push(cb.value);
    });

    const payload = {
        call_date: formData.get('call_date') || null,
        client_name: formData.get('client_name'),
        is_anonymous: formData.get('is_anonymous') === 'on' ? 1 : 0,
        client_gender: formData.get('client_gender'),
        client_age_group: formData.get('client_age_group'),
        client_phone: formData.get('client_phone'),
        client_region: formData.get('client_region'),
        violence_types: violenceTypes,
        perpetrator_relation: formData.get('perpetrator_relation'),
        risk_level: formData.get('risk_level'),
        incident_history: formData.get('incident_history'),
        main_issues: formData.get('main_issues'),
        counseling_content: formData.get('counseling_content'),
        action_types: actionTypes,
        status: formData.get('status'),
        counselor_id: parseInt(formData.get('counselor_id')) || null
    };

    const callId = formData.get('call_id');
    const isEdit = !!callId;
    const url = isEdit ? `/api/calls/${callId}` : '/api/calls';
    const method = isEdit ? 'PUT' : 'POST';

    try {
        const res = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await res.json();
        if (res.ok && result.success) {
            showToast(result.message || '저장되었습니다.');
            closeModal('call-log-modal');
            setTimeout(() => window.location.reload(), 400);
        } else {
            showToast(result.detail || '저장에 실패했습니다.', 'error');
        }
    } catch (err) {
        showToast('서버 통신 오류가 발생했습니다.', 'error');
    }
}

async function openCallDetail(callId) {
    try {
        const res = await fetch(`/api/calls/${callId}`);
        if (!res.ok) throw new Error('상담 조회 실패');
        const call = await res.json();

        document.getElementById('detail-id').innerText = `#${call.id}`;
        document.getElementById('detail-date').innerText = call.call_date;
        document.getElementById('detail-client-name').innerText = call.client_name + (call.is_anonymous ? ' (익명보호)' : '');
        document.getElementById('detail-gender-age').innerText = `${call.client_gender} / ${call.client_age_group || '연령미상'}`;
        document.getElementById('detail-phone').innerText = call.client_phone || '연락처 없음';
        document.getElementById('detail-region').innerText = call.client_region || '지역 미기재';
        document.getElementById('detail-relation').innerText = call.perpetrator_relation;
        document.getElementById('detail-counselor').innerText = call.counselor_name || '미지정';
        
        // 위험도 배지
        const riskBadge = document.getElementById('detail-risk');
        if (call.risk_level === 'HIGH') {
            riskBadge.className = 'px-2.5 py-1 text-xs font-semibold rounded-full bg-rose-100 text-rose-700 border border-rose-300';
            riskBadge.innerText = '긴급위험(HIGH)';
        } else if (call.risk_level === 'MEDIUM') {
            riskBadge.className = 'px-2.5 py-1 text-xs font-semibold rounded-full bg-amber-100 text-amber-700 border border-amber-300';
            riskBadge.innerText = '주의(MEDIUM)';
        } else {
            riskBadge.className = 'px-2.5 py-1 text-xs font-semibold rounded-full bg-emerald-100 text-emerald-700 border border-emerald-300';
            riskBadge.innerText = '일반(LOW)';
        }

        // 진행상태
        document.getElementById('detail-status').innerText = 
            call.status === 'RECEIVED' ? '접수' :
            call.status === 'IN_PROGRESS' ? '진행중' :
            call.status === 'COMPLETED' ? '조치완료' : '추후상담예정';

        // 태그들
        const vContainer = document.getElementById('detail-violence');
        vContainer.innerHTML = (call.violence_types || '').split(',').map(v => 
            `<span class="px-2 py-0.5 bg-rose-50 text-rose-600 rounded text-xs border border-rose-200 font-medium">${v.trim()}</span>`
        ).join(' ');

        const aContainer = document.getElementById('detail-actions');
        aContainer.innerHTML = (call.action_types || '').split(',').map(a => 
            `<span class="px-2 py-0.5 bg-indigo-50 text-indigo-600 rounded text-xs border border-indigo-200 font-medium">${a.trim()}</span>`
        ).join(' ');

        document.getElementById('detail-history').innerText = call.incident_history || '특이사항 없음';
        document.getElementById('detail-issues').innerText = call.main_issues || '-';
        document.getElementById('detail-content').innerText = call.counseling_content || '';

        // 수정 버튼 데이터 바인딩
        const editBtn = document.getElementById('detail-edit-btn');
        if (editBtn) {
            editBtn.onclick = () => {
                closeModal('call-detail-modal');
                editCallLog(call);
            };
        }

        const deleteBtn = document.getElementById('detail-delete-btn');
        if (deleteBtn) {
            deleteBtn.onclick = () => deleteCallLog(call.id);
        }

        openModal('call-detail-modal');
    } catch (e) {
        showToast('상담 상세 정보를 불러오지 못했습니다.', 'error');
    }
}

function editCallLog(call) {
    const form = document.getElementById('call-log-form');
    if (!form) return;

    form.reset();
    form.querySelector("input[name='call_id']").value = call.id;
    form.querySelector("input[name='call_date']").value = call.call_date;
    form.querySelector("input[name='client_name']").value = call.client_name;
    form.querySelector("input[name='is_anonymous']").checked = !!call.is_anonymous;
    form.querySelector("select[name='client_gender']").value = call.client_gender;
    form.querySelector("select[name='client_age_group']").value = call.client_age_group || '30대';
    form.querySelector("input[name='client_phone']").value = call.client_phone || '';
    form.querySelector("input[name='client_region']").value = call.client_region || '';
    form.querySelector("select[name='perpetrator_relation']").value = call.perpetrator_relation;
    form.querySelector("select[name='risk_level']").value = call.risk_level;
    form.querySelector("textarea[name='incident_history']").value = call.incident_history || '';
    form.querySelector("input[name='main_issues']").value = call.main_issues || '';
    form.querySelector("textarea[name='counseling_content']").value = call.counseling_content || '';
    form.querySelector("select[name='status']").value = call.status;
    form.querySelector("select[name='counselor_id']").value = call.counselor_id;

    // 체크박스 세팅
    const vList = (call.violence_types || '').split(',').map(s => s.trim());
    form.querySelectorAll("input[name='violence_types']").forEach(cb => {
        cb.checked = vList.includes(cb.value);
    });

    const aList = (call.action_types || '').split(',').map(s => s.trim());
    form.querySelectorAll("input[name='action_types']").forEach(cb => {
        cb.checked = aList.includes(cb.value);
    });

    document.getElementById('modal-call-title').innerText = '상담 기록 수정';
    openModal('call-log-modal');
}

function openNewCallModal() {
    const form = document.getElementById('call-log-form');
    if (form) {
        form.reset();
        form.querySelector("input[name='call_id']").value = '';
        const now = new Date();
        const y = now.getFullYear();
        const m = String(now.getMonth() + 1).padStart(2, '0');
        const d = String(now.getDate()).padStart(2, '0');
        const h = String(now.getHours()).padStart(2, '0');
        const min = String(now.getMinutes()).padStart(2, '0');
        form.querySelector("input[name='call_date']").value = `${y}-${m}-${d} ${h}:${min}`;
        document.getElementById('modal-call-title').innerText = '신규 전화상담 접수/기록';
    }
    openModal('call-log-modal');
}

async function deleteCallLog(callId) {
    if (!confirm('정말로 이 상담 기록을 삭제하시겠습니까? 삭제된 기록은 복구할 수 없습니다.')) return;
    try {
        const res = await fetch(`/api/calls/${callId}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
            showToast('상담 기록이 삭제되었습니다.');
            closeModal('call-detail-modal');
            setTimeout(() => window.location.reload(), 400);
        } else {
            showToast(data.detail || '삭제 실패', 'error');
        }
    } catch (e) {
        showToast('통신 오류가 발생했습니다.', 'error');
    }
}

// 2. 휴가 신청 관련 함수
async function submitLeaveRequest(event) {
    event.preventDefault();
    const form = event.target;
    const formData = new FormData(form);

    const payload = {
        leave_type: formData.get('leave_type'),
        start_date: formData.get('start_date'),
        end_date: formData.get('end_date'),
        days_count: parseFloat(formData.get('days_count')) || 1.0,
        reason: formData.get('reason'),
        deputy_counselor_id: parseInt(formData.get('deputy_counselor_id')) || null
    };

    try {
        const res = await fetch('/api/leaves', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok && data.success) {
            showToast(data.message);
            closeModal('leave-modal');
            setTimeout(() => window.location.reload(), 400);
        } else {
            showToast(data.detail || '휴가 신청에 실패했습니다.', 'error');
        }
    } catch (e) {
        showToast('서버 오류가 발생했습니다.', 'error');
    }
}

async function processLeave(leaveId, status) {
    let rejectReason = null;
    if (status === 'REJECTED') {
        rejectReason = prompt('반려 사유를 입력해주세요:');
        if (rejectReason === null) return; // 취소
    } else {
        if (!confirm('휴가 신청을 승인하시겠습니까? 잔여 연차가 차감됩니다.')) return;
    }

    try {
        const res = await fetch(`/api/leaves/${leaveId}/process`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: status, reject_reason: rejectReason })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            showToast(data.message);
            setTimeout(() => window.location.reload(), 400);
        } else {
            showToast(data.detail || '처리에 실패했습니다.', 'error');
        }
    } catch (e) {
        showToast('통신 오류가 발생했습니다.', 'error');
    }
}

async function cancelLeave(leaveId) {
    if (!confirm('휴가 신청을 취소하시겠습니까?')) return;
    try {
        const res = await fetch(`/api/leaves/${leaveId}`, { method: 'DELETE' });
        const data = await res.json();
        if (res.ok && data.success) {
            showToast(data.message);
            setTimeout(() => window.location.reload(), 400);
        } else {
            showToast(data.detail || '취소 실패', 'error');
        }
    } catch (e) {
        showToast('통신 오류가 발생했습니다.', 'error');
    }
}

// 3. 상담사 관리 관련 함수
async function submitCounselor(event) {
    event.preventDefault();
    const form = event.target;
    const formData = new FormData(form);
    const counselorId = formData.get('counselor_id');

    const payload = {
        name: formData.get('name'),
        title: formData.get('title'),
        role: formData.get('role'),
        phone: formData.get('phone'),
        email: formData.get('email'),
        specialties: formData.get('specialties'),
        annual_leave_total: parseFloat(formData.get('annual_leave_total')) || 15.0
    };

    if (!counselorId) {
        payload.username = formData.get('username');
        payload.password = formData.get('password') || '1234';
    } else {
        const pwd = formData.get('password');
        if (pwd) payload.password = pwd;
    }

    const url = counselorId ? `/api/counselors/${counselorId}` : '/api/counselors';
    const method = counselorId ? 'PUT' : 'POST';

    try {
        const res = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok && data.success) {
            showToast(data.message);
            closeModal('counselor-modal');
            setTimeout(() => window.location.reload(), 400);
        } else {
            showToast(data.detail || '처리에 실패했습니다.', 'error');
        }
    } catch (e) {
        showToast('통신 오류가 발생했습니다.', 'error');
    }
}

function openNewCounselorModal() {
    const form = document.getElementById('counselor-form');
    if (form) {
        form.reset();
        form.querySelector("input[name='counselor_id']").value = '';
        form.querySelector("input[name='username']").disabled = false;
        form.querySelector("#username-group").style.display = 'block';
        document.getElementById('modal-counselor-title').innerText = '신규 상담사 등록';
    }
    openModal('counselor-modal');
}

function openEditCounselorModal(counselor) {
    const form = document.getElementById('counselor-form');
    if (!form) return;
    form.reset();
    form.querySelector("input[name='counselor_id']").value = counselor.id;
    form.querySelector("input[name='name']").value = counselor.name;
    form.querySelector("input[name='title']").value = counselor.title;
    form.querySelector("select[name='role']").value = counselor.role;
    form.querySelector("input[name='phone']").value = counselor.phone || '';
    form.querySelector("input[name='email']").value = counselor.email || '';
    form.querySelector("input[name='specialties']").value = counselor.specialties || '';
    form.querySelector("input[name='annual_leave_total']").value = counselor.annual_leave_total;
    
    // 수정 시 username 변경 불가
    const usernameGroup = form.querySelector("#username-group");
    if (usernameGroup) usernameGroup.style.display = 'none';

    document.getElementById('modal-counselor-title').innerText = `상담사 정보 수정 (${counselor.name})`;
    openModal('counselor-modal');
}

// 4. 업무일지 관련 함수
async function submitWorkLog(event) {
    event.preventDefault();
    const form = event.target;
    const formData = new FormData(form);

    const payload = {
        log_date: formData.get('log_date'),
        counseling_summary: formData.get('counseling_summary'),
        admin_tasks: formData.get('admin_tasks'),
        crisis_cases: formData.get('crisis_cases'),
        tomorrow_plan: formData.get('tomorrow_plan')
    };

    try {
        const res = await fetch('/api/worklogs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok && data.success) {
            showToast(data.message);
            setTimeout(() => window.location.reload(), 400);
        } else {
            showToast(data.detail || '저장에 실패했습니다.', 'error');
        }
    } catch (e) {
        showToast('통신 오류가 발생했습니다.', 'error');
    }
}

async function submitWorkLogFeedback(logDate) {
    const feedback = prompt('확인 코멘트 및 결재 의견을 작성해주세요:');
    if (feedback === null) return;

    try {
        const res = await fetch(`/api/worklogs/${logDate}/feedback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ feedback: feedback, is_confirmed: 1 })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            showToast(data.message);
            setTimeout(() => window.location.reload(), 400);
        } else {
            showToast(data.detail || '피드백 등록에 실패했습니다.', 'error');
        }
    } catch (e) {
        showToast('통신 오류가 발생했습니다.', 'error');
    }
}

// 5. 마이페이지 정보 수정 함수
async function updateMyProfile(event, myId) {
    event.preventDefault();
    const form = event.target;
    const formData = new FormData(form);

    const payload = {
        name: formData.get('name'),
        phone: formData.get('phone'),
        email: formData.get('email'),
        specialties: formData.get('specialties')
    };

    const pwd = formData.get('password');
    if (pwd && pwd.trim().length > 0) {
        payload.password = pwd.trim();
    }

    try {
        const res = await fetch(`/api/counselors/${myId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (res.ok && data.success) {
            showToast('내 정보가 성공적으로 수정되었습니다.');
            setTimeout(() => window.location.reload(), 400);
        } else {
            showToast(data.detail || '수정에 실패했습니다.', 'error');
        }
    } catch (e) {
        showToast('통신 오류가 발생했습니다.', 'error');
    }
}

// 6. Typebot 챗봇 연동 헬퍼
function saveTypebotId() {
    const input = document.getElementById('typebot-id-input');
    if (!input || !input.value.trim()) {
        showToast('Typebot ID 또는 Slug를 입력해주세요.', 'error');
        return;
    }
    const val = input.value.trim();
    localStorage.setItem('typebot_id', val);
    showToast(`Typebot (${val})이 설정되었습니다. 페이지를 새로고침합니다.`);
    setTimeout(() => window.location.reload(), 500);
}

function removeTypebotId() {
    localStorage.removeItem('typebot_id');
    const input = document.getElementById('typebot-id-input');
    if (input) input.value = '';
    showToast('Typebot 연동이 해제되었습니다.');
    setTimeout(() => window.location.reload(), 500);
}

document.addEventListener('DOMContentLoaded', () => {
    // Typebot 모달 초기화
    const input = document.getElementById('typebot-id-input');
    const saved = localStorage.getItem('typebot_id');
    if (input && saved) input.value = saved;

    const webhookText = document.getElementById('webhook-url-text');
    if (webhookText) {
        webhookText.innerText = `${window.location.origin}/api/webhook/typebot`;
    }
});

// 7. 통화 녹취(Tyro/Tiro) AI 자동 상담일지 채우기
function loadSampleTranscript(type) {
    const textarea = document.getElementById('ai-transcript-input');
    if (!textarea) return;

    if (type === 1) {
        textarea.value = `[전화 통화 녹취 내용 - 11:20 접수]
상담사: 희망가정폭력상담소입니다. 무엇을 도와드릴까요?
내담자: 여보세요... 지금 남편이 술을 마시고 부엌에서 식칼을 들고 죽이겠다고 소리를 질러서, 아이 데리고 급하게 신발도 못 신고 도망 나왔어요.
상담사: 내담자님, 현재 계신 곳은 안전하신가요? 다치신 곳은 없으신가요?
내담자: 근처 편의점에 숨어있는데 너무 무섭고 온몸이 떨려요. 남편이 뺨을 때리고 발로 차서 얼굴과 다리에 멍이 심하게 들었어요.
상담사: 당장 경찰 112 긴급 출동과 신변보호를 먼저 요청해야 합니다. 동의하시나요?
내담자: 네 제발요... 그리고 오늘 밤 집에 못 가는데 아이랑 갈 수 있는 긴급 쉼터가 있을까요?
상담사: 알겠습니다. 관할 경찰서에 긴급 출동 요청을 연계하고, 즉시 입소하실 수 있는 긴급피난처 쉼터 연계를 착수하겠습니다.`;
    } else {
        textarea.value = `[전화 통화 녹취 내용 - 14:05 접수]
상담사: 희망가정폭력상담소입니다.
내담자: 전 남자친구 때문에 미칠 것 같아요. 헤어지자고 했는데 하루에 전화를 100통씩 걸고 직장 앞으로 찾아와요.
상담사: 네, 스토킹과 협박이 동반되고 있는 상황이군요.
내담자: 어제는 제 핸드폰 위치추적 앱을 몰래 깔아둔 걸 알았어요. 욕설 문자를 계속 보내고, 안 만나주면 자살하겠다고 협박해요.
상담사: 이는 명백한 데이트폭력 및 스토킹 범죄에 해당합니다. 증거 수집 방법과 스토킹 처벌법상 잠정조치 신청 및 피해자 무료 법률구조를 안내해 드리겠습니다.`;
    }
}

async function processAiTranscript() {
    const textarea = document.getElementById('ai-transcript-input');
    if (!textarea || !textarea.value.trim()) {
        showToast('통화 내용을 입력해주세요.', 'error');
        return;
    }

    try {
        showToast('AI가 통화 내용을 분석하여 상담일지를 작성 중입니다...', 'info');
        const res = await fetch('/api/calls/analyze-transcript', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ transcript: textarea.value.trim() })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            closeModal('ai-transcript-modal');
            
            // 신규 상담 등록 폼에 데이터 자동 채우기
            openNewCallModal();
            const form = document.getElementById('call-log-form');
            if (form && data.extracted_data) {
                const ext = data.extracted_data;
                form.querySelector("input[name='client_name']").value = ext.client_name;
                form.querySelector("select[name='perpetrator_relation']").value = ext.perpetrator_relation;
                form.querySelector("select[name='risk_level']").value = ext.risk_level;
                form.querySelector("input[name='main_issues']").value = ext.main_issues;
                form.querySelector("textarea[name='counseling_content']").value = ext.counseling_content;

                // 폭력 유형 체크박스
                form.querySelectorAll("input[name='violence_types']").forEach(cb => {
                    cb.checked = ext.violence_types.includes(cb.value);
                });

                // 조치 사항 체크박스
                form.querySelectorAll("input[name='action_types']").forEach(cb => {
                    cb.checked = ext.action_types.includes(cb.value);
                });
            }
            showToast('통화 분석 완료! 내용을 확인하신 후 저장해주세요.');
        } else {
            showToast(data.detail || '분석에 실패했습니다.', 'error');
        }
    } catch (e) {
        showToast('서버 통신 오류가 발생했습니다.', 'error');
    }
}


