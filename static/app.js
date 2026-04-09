/* Upload Manager — Frontend Logic */

const API = '';  // Same origin
let currentUser = null;  // {employee_id, name, role, token}
let topics = [];
let platforms = [];
let platformFields = {};  // {platform_id: [fields]}
let channels = [];
let currentTopic = null;
let currentPlatformId = null;
let copiedFields = new Set();

// ===== API Helper =====
async function api(method, path, body) {
    const opts = { method, headers: { 'Content-Type': 'application/json; charset=utf-8' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(API + path, opts);
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'خطأ في السيرفر');
    }
    return res.json();
}

// ===== Toast =====
function toast(msg, type = '') {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.className = 'toast show ' + type;
    setTimeout(() => el.className = 'toast', 2500);
}

// ===== Modal =====
function showModal(title, body, onConfirm) {
    document.getElementById('modal-title').textContent = title;
    document.getElementById('modal-body').textContent = body;
    document.getElementById('modal').classList.remove('hidden');
    document.getElementById('modal-confirm').onclick = () => {
        closeModal();
        onConfirm();
    };
}
function closeModal() {
    document.getElementById('modal').classList.add('hidden');
}

// ===== PIN Login =====
let pin = '';

function pinInput(n) {
    if (pin.length >= 4) return;
    pin += n;
    updatePinDots();
    if (pin.length === 4) {
        setTimeout(doLogin, 200);
    }
}

function pinDelete() {
    pin = pin.slice(0, -1);
    updatePinDots();
    document.getElementById('login-error').textContent = '';
}

function updatePinDots() {
    for (let i = 0; i < 4; i++) {
        const dot = document.getElementById('dot-' + i);
        if (i < pin.length) {
            dot.textContent = '●';
            dot.classList.add('filled');
        } else {
            dot.textContent = '';
            dot.classList.remove('filled');
        }
    }
}

async function doLogin() {
    try {
        const data = await api('POST', '/api/auth/login', { pin });
        currentUser = data;
        localStorage.setItem('user', JSON.stringify(data));
        showDashboard();
    } catch (e) {
        document.getElementById('login-error').textContent = e.message;
        pin = '';
        updatePinDots();
    }
}

function logout() {
    currentUser = null;
    localStorage.removeItem('user');
    pin = '';
    updatePinDots();
    showScreen('login-screen');
}

// ===== Screen Navigation =====
function showScreen(id) {
    ['login-screen', 'dashboard-screen', 'upload-screen'].forEach(s => {
        document.getElementById(s).classList.toggle('hidden', s !== id);
    });
}

function goBack() {
    showDashboard();
}

// ===== Dashboard =====
async function showDashboard() {
    showScreen('dashboard-screen');
    document.getElementById('user-name').textContent = currentUser.name;

    // Load data in parallel
    let statsData, topicsData, platformsData, channelsData;
    try {
        [statsData, topicsData, platformsData, channelsData] = await Promise.all([
            api('GET', '/api/dashboard/stats'),
            api('GET', '/api/topics?limit=200&status=pending'),
            api('GET', '/api/platforms'),
            api('GET', '/api/channels'),
        ]);
    } catch (e) {
        toast('فشل تحميل البيانات — حاول تاني', 'error');
        return;
    }

    // Stats
    document.getElementById('stat-total').textContent = statsData.total_topics;
    document.getElementById('stat-pending').textContent = statsData.pending_uploads;
    document.getElementById('stat-today').textContent = statsData.uploaded_today;
    document.getElementById('stat-locked').textContent = statsData.locked_now;

    platforms = platformsData;
    channels = channelsData;
    topics = topicsData;

    // Load fields for all platforms in parallel
    try {
        await Promise.all(platforms.map(async p => {
            platformFields[p.id] = await api('GET', `/api/platforms/${p.id}/fields`);
        }));
    } catch (e) {
        toast('فشل تحميل حقول المنصات', 'error');
    }

    renderChannelFilters();
    renderTopicList();
}

let activeChannelFilter = null;

function renderChannelFilters() {
    const container = document.getElementById('channel-filters');
    let html = `<button class="filter-btn ${!activeChannelFilter ? 'active' : ''}" onclick="filterChannel(null)">الكل</button>`;
    for (const ch of channels) {
        const active = activeChannelFilter === ch.id ? 'active' : '';
        html += `<button class="filter-btn ${active}" onclick="filterChannel(${ch.id})">${escapeHtml(ch.display_name || ch.name)}</button>`;
    }
    container.innerHTML = html;
}

function filterChannel(chId) {
    activeChannelFilter = chId;
    renderChannelFilters();
    renderTopicList();
}

function renderTopicList() {
    const container = document.getElementById('topic-list');
    let filtered = topics;
    if (activeChannelFilter) {
        filtered = topics.filter(t => t.channel_id === activeChannelFilter);
    }
    // Only show topics that have pending platforms
    filtered = filtered.filter(t => t.status !== 'completed');

    if (filtered.length === 0) {
        container.innerHTML = '<div class="empty-state"><div class="icon">&#10003;</div><p>مفيش فيديوهات محتاجة رفع</p></div>';
        return;
    }

    let html = '';
    for (const t of filtered) {
        const ch = channels.find(c => c.id === t.channel_id);
        const chName = escapeHtml(ch ? (ch.display_name || ch.name) : '');
        const badges = (t.platform_data || []).map(pd => {
            const pl = platforms.find(p => p.id === pd.platform_id);
            const plName = pl ? (pl.display_name || pl.name) : pd.platform_id;
            return `<span class="badge ${pd.upload_status}">${escapeHtml(plName)}</span>`;
        }).join('');

        // Find next scheduled time
        let timeStr = '';
        const nextPd = (t.platform_data || []).find(pd => pd.scheduled_time && pd.upload_status !== 'uploaded');
        if (nextPd) {
            timeStr = formatDate(nextPd.scheduled_time);
        }

        html += `
        <div class="topic-card" onclick="openTopic(${t.id})">
            <div class="topic-top">
                <span class="topic-number">#${t.topic_number}</span>
                <span class="topic-channel">${chName}</span>
            </div>
            <div class="topic-title">${escapeHtml(t.title || 'بدون عنوان')}</div>
            <div class="platform-badges">${badges}</div>
            ${timeStr ? `<div class="topic-time">&#128337; ${timeStr}</div>` : ''}
        </div>`;
    }
    container.innerHTML = html;
}

// ===== Upload Screen =====
async function openTopic(topicId) {
    try {
        currentTopic = await api('GET', `/api/topics/${topicId}`);
    } catch (e) {
        toast(e.message, 'error');
        return;
    }

    showScreen('upload-screen');
    copiedFields = new Set();

    const ch = channels.find(c => c.id === currentTopic.channel_id);
    document.getElementById('upload-title').textContent = `#${currentTopic.topic_number}`;
    document.getElementById('upload-topic-title').textContent = currentTopic.title || 'بدون عنوان';
    document.getElementById('upload-meta').textContent =
        `${ch ? (ch.display_name || ch.name) : ''} | ${currentTopic.content_type}`;

    renderPlatformTabs();

    // Select first pending platform
    const firstPending = (currentTopic.platform_data || []).find(pd => pd.upload_status !== 'uploaded');
    if (firstPending) {
        selectPlatform(firstPending.platform_id);
    } else {
        currentPlatformId = null;
        document.getElementById('fields-section').innerHTML = '<div class="empty-state"><div class="icon">&#10003;</div><p>كل المنصات اترفعت</p></div>';
        document.getElementById('confirm-section').style.display = 'none';
    }
}

function renderPlatformTabs() {
    const container = document.getElementById('platform-tabs');
    let html = '';
    for (const pd of (currentTopic.platform_data || [])) {
        const pl = platforms.find(p => p.id === pd.platform_id);
        const plName = pl ? (pl.display_name || pl.name) : '';
        let cls = '';
        if (pd.upload_status === 'uploaded') cls = 'uploaded';
        else if (pd.upload_status === 'locked' && pd.lock_holder !== currentUser.employee_id) cls = 'locked-other';
        else if (pd.platform_id === currentPlatformId) cls = 'active';
        html += `<button class="platform-tab ${cls}" onclick="selectPlatform(${pd.platform_id})" ${pd.upload_status === 'uploaded' ? 'disabled' : ''}>${escapeHtml(plName)}${pd.upload_status === 'uploaded' ? ' ✓' : ''}</button>`;
    }
    container.innerHTML = html;
}

async function selectPlatform(platformId) {
    const pd = (currentTopic.platform_data || []).find(p => p.platform_id === platformId);
    if (!pd || pd.upload_status === 'uploaded') return;

    // Lock
    if (pd.upload_status !== 'locked' || pd.lock_holder !== currentUser.employee_id) {
        try {
            await api('POST', `/api/topics/${currentTopic.id}/platforms/${platformId}/lock`, { employee_id: currentUser.employee_id });
        } catch (e) {
            toast(e.message, 'error');
            return;
        }
        // Refresh topic data
        try {
            currentTopic = await api('GET', `/api/topics/${currentTopic.id}`);
        } catch (e2) {
            toast('فشل تحديث البيانات — حاول تاني', 'error');
            return;
        }
    }

    currentPlatformId = platformId;
    copiedFields = new Set();
    renderPlatformTabs();
    renderFields();
}

function renderFields() {
    const pd = (currentTopic.platform_data || []).find(p => p.platform_id === currentPlatformId);
    if (!pd) return;

    const fields = platformFields[currentPlatformId] || [];
    let values = {};
    try { values = JSON.parse(pd.field_values || '{}'); } catch (e) {}

    // Schedule time
    const schedSection = document.getElementById('schedule-section');
    const schedTime = pd.scheduled_time ? new Date(pd.scheduled_time) : null;
    // Use local time for datetime-local input (not UTC)
    const schedIso = schedTime ? (schedTime.getFullYear() + '-' + String(schedTime.getMonth()+1).padStart(2,'0') + '-' + String(schedTime.getDate()).padStart(2,'0') + 'T' + String(schedTime.getHours()).padStart(2,'0') + ':' + String(schedTime.getMinutes()).padStart(2,'0')) : '';
    schedSection.innerHTML = `
    <div class="schedule-card">
        <div class="time-label">موعد النشر</div>
        <div class="time-value" id="sched-display">${schedTime ? formatDate(pd.scheduled_time) : 'مش محدد'}</div>
        <button class="copy-btn" onclick="toggleScheduleEdit()" style="margin-top:6px">تعديل الموعد</button>
        <div id="sched-edit" style="display:none;margin-top:8px">
            <input type="datetime-local" id="sched-input" value="${schedIso}" dir="ltr"
                style="padding:8px 12px;font-size:14px;border:1px solid #ddd;border-radius:8px;width:100%">
            <div style="display:flex;gap:8px;margin-top:8px">
                <button class="copy-btn" onclick="saveScheduleTime()" style="background:#4f46e5;color:#fff">حفظ</button>
                <button class="copy-btn" onclick="clearScheduleTime()" style="background:#ef4444;color:#fff">إزالة الموعد</button>
            </div>
        </div>
    </div>`;

    // Fields
    const container = document.getElementById('fields-section');
    if (fields.length === 0 && Object.keys(values).length === 0) {
        container.innerHTML = '<div class="empty-state"><p>مفيش بيانات لسه</p></div>';
        document.getElementById('confirm-section').style.display = 'none';
        return;
    }

    let html = '';
    for (const f of fields) {
        const val = values[f.field_name] || '';
        const isCopied = copiedFields.has(f.field_name);
        const displayVal = Array.isArray(val) ? val.join(', ') : (val || '—');

        const safeName = escapeHtml(f.field_name).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        html += `
        <div class="field-card ${isCopied ? 'copied' : ''}" id="field-${safeName}">
            <div class="field-label">
                <span>${escapeHtml(f.field_label || f.field_name)} ${f.is_required ? '<span class="required">*</span>' : ''}</span>
                ${isCopied ? '<span class="copied-badge">تم النسخ ✓</span>' : ''}
            </div>
            <div class="field-value">${escapeHtml(displayVal)}</div>
            ${f.is_copyable && val ? `<button class="copy-btn ${isCopied ? 'copied' : ''}" onclick="copyField('${safeName}', this)">${isCopied ? 'تم النسخ ✓' : 'نسخ'}</button>` : ''}
        </div>`;
    }
    container.innerHTML = html;

    // TikTok button — show only when platform is TikTok and has video
    const currentPlatform = platforms.find(p => p.id === currentPlatformId);
    const tiktokSection = document.getElementById('tiktok-section');
    if (tiktokSection) {
        if (currentPlatform && currentPlatform.name.toLowerCase() === 'tiktok' && currentTopic.video_path) {
            tiktokSection.style.display = '';
            tiktokSection.innerHTML = `
                <button class="tiktok-btn" id="tiktok-btn" onclick="onTikTokUpload()">
                    رفع على تيكتوك
                </button>
                <div class="tiktok-hint">بيفتح متصفح ويملى البيانات تلقائي</div>`;
        } else {
            tiktokSection.style.display = 'none';
        }
    }

    // Confirm section
    document.getElementById('confirm-section').style.display = '';
    updateConfirmState();
}

async function copyField(fieldName, btn) {
    const pd = (currentTopic.platform_data || []).find(p => p.platform_id === currentPlatformId);
    if (!pd) return;

    let values = {};
    try { values = JSON.parse(pd.field_values || '{}'); } catch (e) {}
    const val = values[fieldName];
    const text = Array.isArray(val) ? val.join(', ') : (val || '');

    try {
        // Try modern Clipboard API first, fallback to execCommand for HTTP
        let copyOk = false;
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(text);
            copyOk = true;
        } else {
            // Fallback for HTTP (non-secure context)
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.left = '-9999px';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.select();
            copyOk = document.execCommand('copy');
            document.body.removeChild(ta);
        }
        if (!copyOk) throw new Error('copy failed');

        copiedFields.add(fieldName);

        // Log copy
        api('POST', `/api/topics/${currentTopic.id}/platforms/${currentPlatformId}/copy-log`, {
            employee_id: currentUser.employee_id,
            field_name: fieldName,
        }).catch(() => {});

        // Update UI
        const card = document.getElementById('field-' + fieldName);
        if (card) card.classList.add('copied');
        if (btn) {
            btn.textContent = 'تم النسخ ✓';
            btn.classList.add('copied');
        }
        // Add copied badge
        const labelDiv = card?.querySelector('.field-label');
        if (labelDiv && !labelDiv.querySelector('.copied-badge')) {
            const badge = document.createElement('span');
            badge.className = 'copied-badge';
            badge.textContent = 'تم النسخ ✓';
            labelDiv.appendChild(badge);
        }

        toast('تم النسخ', 'success');
        updateConfirmState();
    } catch (e) {
        toast('فشل النسخ — حاول تاني', 'error');
    }
}

function toggleScheduleEdit() {
    const el = document.getElementById('sched-edit');
    el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

async function saveScheduleTime() {
    const val = document.getElementById('sched-input').value;
    if (!val) { toast('اختار تاريخ ووقت', 'error'); return; }
    try {
        const res = await api('PATCH', `/api/topics/${currentTopic.id}/platforms/${currentPlatformId}/schedule`, {
            scheduled_time: val + ':00',
        });
        // Update local data
        const pd = (currentTopic.platform_data || []).find(p => p.platform_id === currentPlatformId);
        if (pd) pd.scheduled_time = res.scheduled_time;
        renderFields();
        toast('تم تعديل الموعد', 'success');
    } catch (e) {
        toast(e.message || 'فشل التعديل', 'error');
    }
}

async function clearScheduleTime() {
    if (!confirm('إزالة موعد النشر لهذه المنصة؟')) return;
    try {
        const res = await api('PATCH', `/api/topics/${currentTopic.id}/platforms/${currentPlatformId}/schedule`, {
            scheduled_time: null,
        });
        const pd = (currentTopic.platform_data || []).find(p => p.platform_id === currentPlatformId);
        if (pd) pd.scheduled_time = null;
        renderFields();
        toast('تم إزالة الموعد', 'success');
    } catch (e) {
        toast(e.message || 'فشل الإزالة', 'error');
    }
}

function updateConfirmState() {
    const fields = platformFields[currentPlatformId] || [];
    const requiredFields = fields.filter(f => f.is_required && f.is_copyable);
    const pd = (currentTopic.platform_data || []).find(p => p.platform_id === currentPlatformId);
    let values = {};
    try { values = JSON.parse(pd?.field_values || '{}'); } catch (e) {}

    // Only count required fields that have values
    const requiredWithValues = requiredFields.filter(f => {
        const v = values[f.field_name];
        return v && (Array.isArray(v) ? v.length > 0 : v.toString().trim() !== '');
    });

    const copied = requiredWithValues.filter(f => copiedFields.has(f.field_name)).length;
    const total = requiredWithValues.length;

    const progressEl = document.getElementById('confirm-progress');
    const btnEl = document.getElementById('confirm-btn');

    if (total === 0) {
        // No required copyable fields with values — allow confirm directly
        progressEl.textContent = '';
        btnEl.disabled = false;
    } else {
        progressEl.textContent = `تم نسخ ${copied} من ${total} حقول إجبارية`;
        btnEl.disabled = copied < total;
    }
}

function onConfirmClick() {
    const pl = platforms.find(p => p.id === currentPlatformId);
    const plName = pl ? (pl.display_name || pl.name) : '';
    showModal(
        'تأكيد الرفع',
        `هل رفعت فيديو "${currentTopic.title || '#' + currentTopic.topic_number}" على ${plName}؟`,
        doConfirmUpload
    );
}

async function doConfirmUpload() {
    try {
        await api('POST', `/api/topics/${currentTopic.id}/platforms/${currentPlatformId}/confirm`, {
            employee_id: currentUser.employee_id,
        });
        toast('تم تأكيد الرفع بنجاح', 'success');

        // Refresh topic
        currentTopic = await api('GET', `/api/topics/${currentTopic.id}`);
        renderPlatformTabs();

        // Select next pending platform
        const nextPending = (currentTopic.platform_data || []).find(pd => pd.upload_status !== 'uploaded');
        if (nextPending) {
            selectPlatform(nextPending.platform_id);
        } else {
            document.getElementById('fields-section').innerHTML = '<div class="empty-state"><div class="icon">&#10003;</div><p>كل المنصات اترفعت! ممتاز</p></div>';
            document.getElementById('confirm-section').style.display = 'none';
            document.getElementById('schedule-section').innerHTML = '';
        }
    } catch (e) {
        toast(e.message, 'error');
    }
}

// ===== TikTok Upload =====
async function onTikTokUpload() {
    const btn = document.getElementById('tiktok-btn');
    if (!btn || btn.disabled) return;
    btn.disabled = true;
    btn.textContent = 'جاري الفتح...';

    try {
        const result = await api('POST', `/api/tiktok/upload/${currentTopic.id}/${currentPlatformId}`, {
            employee_id: currentUser.employee_id,
        });
        if (result.status === 'error') {
            toast(result.message, 'error');
        } else {
            toast(result.message, 'success');
        }
    } catch (e) {
        toast(e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'رفع على تيكتوك';
    }
}

// ===== Helpers =====
function formatDate(dt) {
    if (!dt) return '';
    const d = new Date(dt);
    const days = ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت'];
    const months = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'];
    const h = d.getHours();
    const m = d.getMinutes().toString().padStart(2, '0');
    const ampm = h >= 12 ? 'مساءً' : 'صباحاً';
    const h12 = h % 12 || 12;
    return `${days[d.getDay()]} ${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()} — ${h12}:${m} ${ampm}`;
}

function escapeHtml(s) {
    if (s === null || s === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(s);
    return div.innerHTML.replace(/"/g, '&quot;');
}

// ===== Init =====
(async function init() {
    const saved = localStorage.getItem('user');
    if (saved) {
        try {
            const parsed = JSON.parse(saved);
            if (parsed && parsed.employee_id && parsed.name) {
                // Re-validate employee is still active
                try {
                    const emp = await api('GET', `/api/employees/${parsed.employee_id}`);
                    if (emp && emp.is_active) {
                        currentUser = parsed;
                        showDashboard();
                        return;
                    }
                } catch (e) { /* employee deleted or server down */ }
                localStorage.removeItem('user');
            } else {
                localStorage.removeItem('user');
            }
        } catch (e) {
            localStorage.removeItem('user');
        }
    }
    showScreen('login-screen');
})();
