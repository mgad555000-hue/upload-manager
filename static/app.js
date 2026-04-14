/* Upload Manager — Frontend Logic (v2: Channel → Platform → Content Type → Topics) */

const API = '';  // Same origin
let currentUser = null;  // {employee_id, name, role, token}
let topics = [];
let platforms = [];
let platformFields = {};  // {platform_id: [fields]}
let channels = [];
let currentTopic = null;
let copiedFields = new Set();
let forcedConfirmPending = false; // Track if forced confirm is showing

// Navigation state
let selectedChannel = null;   // {id, name, display_name, ...}
let selectedPlatform = null;  // {platform_id, name, display_name, ...}
let selectedContentType = null; // "shorts" or "long"

// ===== API Helper =====
async function api(method, path, body) {
    const headers = { 'Content-Type': 'application/json; charset=utf-8' };
    if (currentUser && currentUser.token) {
        headers['Authorization'] = 'Bearer ' + currentUser.token;
    }
    const opts = { method, headers };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(API + path, opts);
    if (res.status === 401) {
        localStorage.removeItem('user');
        currentUser = null;
        showScreen('login-screen');
        throw new Error('الجلسة انتهت — سجل دخول من جديد');
    }
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
        goToChannels();
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
    selectedChannel = null;
    selectedPlatform = null;
    selectedContentType = null;
    showScreen('login-screen');
}

// ===== Screen Navigation =====
function showScreen(id) {
    ['login-screen', 'channel-screen', 'platform-screen', 'content-screen', 'topics-screen', 'upload-screen'].forEach(s => {
        document.getElementById(s).classList.toggle('hidden', s !== id);
    });
}

// ===== 1. Channel Selection =====
async function goToChannels() {
    showScreen('channel-screen');
    const nameEl = document.getElementById('user-name-ch');
    if (nameEl) nameEl.textContent = currentUser.name;

    selectedChannel = null;
    selectedPlatform = null;
    selectedContentType = null;

    const container = document.getElementById('channel-list');
    container.innerHTML = '<div class="loading">جاري التحميل...</div>';

    try {
        const data = await api('GET', '/api/nav/channel-counts');
        let html = '';
        for (const ch of data) {
            html += `
            <div class="nav-card" onclick="selectChannel(${ch.channel_id}, '${escapeAttr(ch.name)}', '${escapeAttr(ch.display_name)}')">
                <div class="nav-card-title">${escapeHtml(ch.display_name)}</div>
                <div class="nav-card-meta">${escapeHtml(ch.name)}</div>
                <div class="nav-card-counts">
                    <span class="nav-count pending">${ch.pending} معلق</span>
                    <span class="nav-count total">${ch.total} موضوع</span>
                </div>
            </div>`;
        }
        if (data.length === 0) {
            html = '<div class="empty-state"><p>مفيش قنوات</p></div>';
        }
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<div class="empty-state"><p>فشل التحميل — حاول تاني</p></div>';
        toast(e.message, 'error');
    }
}

function selectChannel(id, name, displayName) {
    selectedChannel = { id, name, display_name: displayName };
    goToPlatforms();
}

// ===== 2. Platform Selection =====
async function goToPlatforms() {
    if (!selectedChannel) { goToChannels(); return; }
    showScreen('platform-screen');

    selectedPlatform = null;
    selectedContentType = null;

    document.getElementById('platform-subtitle').textContent = selectedChannel.display_name;

    const container = document.getElementById('platform-list');
    container.innerHTML = '<div class="loading">جاري التحميل...</div>';

    try {
        const data = await api('GET', `/api/nav/platform-counts/${selectedChannel.id}`);
        let html = '';
        const icons = { youtube: '▶', tiktok: '♪', facebook: 'f', upscrolled: '↑' };
        for (const pl of data) {
            if (pl.total === 0) continue; // Skip platforms with no topics
            const icon = icons[pl.name.toLowerCase()] || '●';
            html += `
            <div class="nav-card platform-card" onclick="selectPlatform(${pl.platform_id}, '${escapeAttr(pl.name)}', '${escapeAttr(pl.display_name)}', '${escapeAttr(pl.mode)}')">
                <div class="nav-card-icon">${icon}</div>
                <div class="nav-card-title">${escapeHtml(pl.display_name)}</div>
                <div class="nav-card-meta">${pl.mode === 'auto' ? 'أوتوماتيك' : 'يدوي'}</div>
                <div class="nav-card-counts">
                    <span class="nav-count pending">${pl.pending} معلق</span>
                    <span class="nav-count total">${pl.total} موضوع</span>
                </div>
            </div>`;
        }
        if (html === '') {
            html = '<div class="empty-state"><p>مفيش مواضيع في القناة دي</p></div>';
        }
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<div class="empty-state"><p>فشل التحميل</p></div>';
        toast(e.message, 'error');
    }
}

function selectPlatform(id, name, displayName, mode) {
    selectedPlatform = { platform_id: id, name, display_name: displayName, mode };
    goToContentType();
}

// ===== 3. Content Type Selection =====
async function goToContentType() {
    if (!selectedChannel || !selectedPlatform) { goToPlatforms(); return; }
    showScreen('content-screen');

    selectedContentType = null;

    document.getElementById('content-subtitle').textContent =
        selectedChannel.display_name + ' → ' + selectedPlatform.display_name;

    const container = document.getElementById('content-list');
    container.innerHTML = '<div class="loading">جاري التحميل...</div>';

    try {
        const data = await api('GET', `/api/nav/content-counts/${selectedChannel.id}/${selectedPlatform.platform_id}`);
        let html = '';
        const labels = { shorts: 'شورتس (Shorts)', long: 'فيديو طويل (Long)' };
        const icons = { shorts: '⚡', long: '🎬' };
        for (const ct of data) {
            if (ct.total === 0) continue;
            html += `
            <div class="nav-card content-card" onclick="selectContentType('${ct.content_type}')">
                <div class="nav-card-icon">${icons[ct.content_type] || ''}</div>
                <div class="nav-card-title">${labels[ct.content_type] || ct.content_type}</div>
                <div class="nav-card-counts">
                    <span class="nav-count pending">${ct.pending} معلق</span>
                    <span class="nav-count total">${ct.total} موضوع</span>
                </div>
            </div>`;
        }
        if (html === '') {
            html = '<div class="empty-state"><p>مفيش مواضيع</p></div>';
        }
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<div class="empty-state"><p>فشل التحميل</p></div>';
        toast(e.message, 'error');
    }
}

function selectContentType(ct) {
    selectedContentType = ct;
    showTopics();
}

// ===== 4. Topic List =====
async function showTopics() {
    if (!selectedChannel || !selectedPlatform || !selectedContentType) { goToContentType(); return; }
    showScreen('topics-screen');

    const ctLabel = selectedContentType === 'shorts' ? 'شورتس' : 'لونج';
    document.getElementById('topics-screen-title').textContent =
        selectedPlatform.display_name + ' — ' + ctLabel;

    // Breadcrumb path
    document.getElementById('nav-path').innerHTML =
        `<span>${escapeHtml(selectedChannel.display_name)}</span> → <span>${escapeHtml(selectedPlatform.display_name)}</span> → <span>${ctLabel}</span>`;

    const container = document.getElementById('topic-list');
    container.innerHTML = '<div class="loading">جاري التحميل...</div>';

    try {
        // Load stats, topics, and platform fields in parallel
        const [statsData, topicsData] = await Promise.all([
            api('GET', `/api/dashboard/stats?channel_id=${selectedChannel.id}&platform_id=${selectedPlatform.platform_id}&content_type=${selectedContentType}`),
            api('GET', `/api/topics?channel_id=${selectedChannel.id}&platform_id=${selectedPlatform.platform_id}&content_type=${selectedContentType}&limit=500`),
        ]);

        // Load fields for selected platform
        if (!platformFields[selectedPlatform.platform_id]) {
            platformFields[selectedPlatform.platform_id] = await api('GET', `/api/platforms/${selectedPlatform.platform_id}/fields`);
        }

        // Stats
        document.getElementById('stat-total').textContent = statsData.total_topics;
        document.getElementById('stat-pending').textContent = statsData.pending_uploads;
        document.getElementById('stat-today').textContent = statsData.uploaded_today;
        document.getElementById('stat-locked').textContent = statsData.locked_now;

        topics = topicsData;
        renderTopicList();
    } catch (e) {
        container.innerHTML = '<div class="empty-state"><p>فشل تحميل البيانات</p></div>';
        toast(e.message, 'error');
    }
}

function renderTopicList() {
    const container = document.getElementById('topic-list');

    if (topics.length === 0) {
        container.innerHTML = '<div class="empty-state"><div class="icon">&#10003;</div><p>مفيش مواضيع</p></div>';
        return;
    }

    let html = '';
    for (const t of topics) {
        // Find platform_data for the selected platform only
        const pd = (t.platform_data || []).find(p => p.platform_id === selectedPlatform.platform_id);
        if (!pd) continue;

        const isUploaded = pd.upload_status === 'uploaded';
        const isLocked = pd.upload_status === 'locked';
        const statusClass = isUploaded ? 'topic-uploaded' : (isLocked ? 'topic-locked' : '');
        const statusBadge = isUploaded
            ? '<span class="topic-status-badge uploaded">تم الرفع ✓</span>'
            : isLocked
                ? '<span class="topic-status-badge locked">مقفول</span>'
                : '<span class="topic-status-badge pending">معلق</span>';

        // Scheduled time
        let timeStr = '';
        if (pd.scheduled_time && !isUploaded) {
            timeStr = formatDate(pd.scheduled_time);
        }

        // Admin can open uploaded topics to revert them
        const isAdmin = currentUser && currentUser.role === 'admin';
        const canClick = !isUploaded || isAdmin;

        html += `
        <div class="topic-card ${statusClass}" onclick="${canClick ? `openTopic(${t.id})` : ''}" ${canClick ? '' : 'style="cursor:default"'}>
            <div class="topic-top">
                <span class="topic-number">#${t.topic_number}</span>
                ${statusBadge}
            </div>
            <div class="topic-title">${escapeHtml(t.title || 'بدون عنوان')}</div>
            ${timeStr ? `<div class="topic-time">&#128337; ${timeStr}</div>` : ''}
            ${isUploaded && pd.uploaded_at ? `<div class="topic-time uploaded-time">تم الرفع: ${formatDate(pd.uploaded_at)}</div>` : ''}
            ${isUploaded && isAdmin ? '<div class="topic-time" style="color:var(--primary)">اضغط للتعديل (أدمن)</div>' : ''}
        </div>`;
    }

    if (html === '') {
        container.innerHTML = '<div class="empty-state"><p>مفيش مواضيع</p></div>';
    } else {
        container.innerHTML = html;
    }
}

// ===== 5. Upload Screen =====
async function openTopic(topicId) {
    if (!selectedPlatform) return;

    try {
        currentTopic = await api('GET', `/api/topics/${topicId}`);
    } catch (e) {
        toast(e.message, 'error');
        return;
    }

    const pd = (currentTopic.platform_data || []).find(p => p.platform_id === selectedPlatform.platform_id);
    if (!pd) {
        toast('المنصة مش موجودة في الموضوع ده', 'error');
        return;
    }

    const isAdmin = currentUser && currentUser.role === 'admin';
    const isUploaded = pd.upload_status === 'uploaded';

    // Non-admin can't open uploaded topics
    if (isUploaded && !isAdmin) {
        toast('الموضوع ده اترفع بالفعل', 'error');
        return;
    }

    showScreen('upload-screen');
    copiedFields = new Set();

    document.getElementById('upload-title').textContent = `#${currentTopic.topic_number} — ${selectedPlatform.display_name}`;
    document.getElementById('upload-topic-title').textContent = currentTopic.title || 'بدون عنوان';
    document.getElementById('upload-meta').textContent =
        `${selectedChannel.display_name} | ${selectedPlatform.display_name} | ${selectedContentType === 'shorts' ? 'شورتس' : 'لونج'}`;

    if (isUploaded) {
        // Admin viewing uploaded topic — show read-only fields + revert button
        renderUploadedView(pd);
        return;
    }

    // Auto-lock for non-uploaded topics
    if (pd.upload_status !== 'locked' || pd.lock_holder !== currentUser.employee_id) {
        try {
            await api('POST', `/api/topics/${currentTopic.id}/platforms/${selectedPlatform.platform_id}/lock`, { employee_id: currentUser.employee_id });
        } catch (e) {
            toast(e.message, 'error');
            goBack();
            return;
        }
        // Refresh
        try {
            currentTopic = await api('GET', `/api/topics/${currentTopic.id}`);
        } catch (e2) {
            toast('فشل تحديث البيانات', 'error');
            goBack();
            return;
        }
    }

    renderFields();
}

function renderUploadedView(pd) {
    const fields = platformFields[selectedPlatform.platform_id] || [];
    let values = {};
    try { values = JSON.parse(pd.field_values || '{}'); } catch (e) {}

    // Schedule section — show uploaded time
    const schedSection = document.getElementById('schedule-section');
    schedSection.innerHTML = `
    <div class="schedule-card" style="border-color:#065f46">
        <div class="time-label">حالة الرفع</div>
        <div class="time-value" style="color:var(--success)">تم الرفع ✓</div>
        ${pd.uploaded_at ? `<div style="font-size:12px;color:var(--text2);margin-top:6px">تاريخ الرفع: ${formatDate(pd.uploaded_at)}</div>` : ''}
    </div>`;

    // Fields — read-only (no copy buttons)
    const container = document.getElementById('fields-section');
    let html = '';
    for (const f of fields) {
        const val = values[f.field_name] || '';
        const displayVal = Array.isArray(val) ? val.join(', ') : (val || '—');
        html += `
        <div class="field-card" style="opacity:0.7">
            <div class="field-label">
                <span>${escapeHtml(f.field_label || f.field_name)}</span>
            </div>
            <div class="field-value">${escapeHtml(displayVal)}</div>
        </div>`;
    }
    container.innerHTML = html;

    // Hide TikTok section
    const tiktokSection = document.getElementById('tiktok-section');
    if (tiktokSection) tiktokSection.style.display = 'none';

    // Confirm section — show revert button instead
    const confirmSection = document.getElementById('confirm-section');
    confirmSection.style.display = '';
    document.getElementById('confirm-progress').textContent = '';
    const btnEl = document.getElementById('confirm-btn');
    btnEl.textContent = 'إلغاء الرفع — إرجاع لـ "معلق"';
    btnEl.disabled = false;
    btnEl.style.background = 'var(--danger)';
    btnEl.style.color = '#fff';
    btnEl.onclick = onRevertClick;
}

function onRevertClick() {
    const plName = selectedPlatform.display_name;
    const topicTitle = currentTopic.title || '#' + currentTopic.topic_number;

    showModal(
        'إلغاء الرفع',
        `هل تريد إرجاع "${topicTitle}" على ${plName} لحالة "معلق"؟`,
        () => {
            showModal(
                'تأكيد نهائي',
                `تأكد: هيتم إلغاء حالة الرفع لـ "${topicTitle}" على ${plName}. الموضوع هيرجع "معلق" وهيحتاج يترفع تاني.`,
                doRevertUpload
            );
        }
    );
}

async function doRevertUpload() {
    try {
        await api('POST', `/api/topics/${currentTopic.id}/platforms/${selectedPlatform.platform_id}/revert-upload`);
        toast('تم إلغاء الرفع — الموضوع رجع معلق', 'success');
        showTopics();
    } catch (e) {
        toast(e.message, 'error');
    }
}

function goBack() {
    if (forcedConfirmPending) return; // Can't go back while forced confirm is pending
    closeForcedConfirm();
    showTopics();
}

function renderFields() {
    const pd = (currentTopic.platform_data || []).find(p => p.platform_id === selectedPlatform.platform_id);
    if (!pd) return;

    const fields = platformFields[selectedPlatform.platform_id] || [];
    let values = {};
    try { values = JSON.parse(pd.field_values || '{}'); } catch (e) {}

    // Schedule time
    const schedSection = document.getElementById('schedule-section');
    const schedTime = pd.scheduled_time ? new Date(pd.scheduled_time) : null;
    const schedIso = schedTime ? (schedTime.getFullYear() + '-' + String(schedTime.getMonth()+1).padStart(2,'0') + '-' + String(schedTime.getDate()).padStart(2,'0') + 'T' + String(schedTime.getHours()).padStart(2,'0') + ':' + String(schedTime.getMinutes()).padStart(2,'0')) : '';
    const isAdmin = currentUser && currentUser.role === 'admin';
    schedSection.innerHTML = `
    <div class="schedule-card">
        <div class="time-label">موعد النشر</div>
        <div class="time-value" id="sched-display">${schedTime ? formatDate(pd.scheduled_time) : 'مش محدد'}</div>
        ${isAdmin ? `<button class="copy-btn" onclick="toggleScheduleEdit()" style="margin-top:6px">تعديل الموعد</button>
        <div id="sched-edit" style="display:none;margin-top:8px">
            <input type="datetime-local" id="sched-input" value="${schedIso}" dir="ltr"
                style="padding:8px 12px;font-size:14px;border:1px solid #ddd;border-radius:8px;width:100%">
            <select id="sched-cascade" style="padding:8px 12px;font-size:13px;border:1px solid #ddd;border-radius:8px;width:100%;margin-top:6px">
                <option value="false">هذا الفيديو فقط</option>
                <option value="true">هذا الفيديو + كل اللي بعده (متتالي)</option>
            </select>
            <div style="display:flex;gap:8px;margin-top:8px">
                <button class="copy-btn" onclick="saveScheduleTime()" style="background:#4f46e5;color:#fff">حفظ</button>
                <button class="copy-btn" onclick="clearScheduleTime()" style="background:#ef4444;color:#fff">إزالة الموعد</button>
            </div>
        </div>` : ''}
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

    // TikTok button
    const tiktokSection = document.getElementById('tiktok-section');
    if (tiktokSection) {
        if (selectedPlatform.name.toLowerCase() === 'tiktok' && currentTopic.video_path) {
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

    // Confirm section — reset button state (may have been changed by renderUploadedView)
    document.getElementById('confirm-section').style.display = '';
    const btnEl = document.getElementById('confirm-btn');
    btnEl.textContent = 'تأكيد تم الرفع';
    btnEl.style.background = '';
    btnEl.style.color = '';
    btnEl.onclick = null; // Let HTML onclick="onConfirmClick()" take over
    updateConfirmState();
}

async function copyField(fieldName, btn) {
    const pd = (currentTopic.platform_data || []).find(p => p.platform_id === selectedPlatform.platform_id);
    if (!pd) return;

    let values = {};
    try { values = JSON.parse(pd.field_values || '{}'); } catch (e) {}
    const val = values[fieldName];
    const text = Array.isArray(val) ? val.join(', ') : (val || '');

    try {
        let copyOk = false;
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(text);
            copyOk = true;
        } else {
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
        api('POST', `/api/topics/${currentTopic.id}/platforms/${selectedPlatform.platform_id}/copy-log`, {
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
    const cascadeEl = document.getElementById('sched-cascade');
    const cascade = cascadeEl ? cascadeEl.value === 'true' : false;

    if (cascade) {
        try {
            const res = await api('POST', '/api/schedule/reschedule', {
                topic_id: currentTopic.id,
                platform_id: selectedPlatform.platform_id,
                new_time: val + ':00',
                cascade: true,
            });
            const pd = (currentTopic.platform_data || []).find(p => p.platform_id === selectedPlatform.platform_id);
            if (pd) pd.scheduled_time = val + ':00';
            renderFields();
            toast(`تم تعديل ${res.changed} فيديو`, 'success');
        } catch (e) {
            toast(e.message || 'فشل التعديل', 'error');
        }
    } else {
        try {
            const res = await api('PATCH', `/api/topics/${currentTopic.id}/platforms/${selectedPlatform.platform_id}/schedule`, {
                scheduled_time: val + ':00',
            });
            const pd = (currentTopic.platform_data || []).find(p => p.platform_id === selectedPlatform.platform_id);
            if (pd) pd.scheduled_time = res.scheduled_time;
            renderFields();
            toast('تم تعديل الموعد', 'success');
        } catch (e) {
            toast(e.message || 'فشل التعديل', 'error');
        }
    }
}

async function clearScheduleTime() {
    if (!confirm('إزالة موعد النشر لهذه المنصة؟')) return;
    try {
        const res = await api('PATCH', `/api/topics/${currentTopic.id}/platforms/${selectedPlatform.platform_id}/schedule`, {
            scheduled_time: null,
        });
        const pd = (currentTopic.platform_data || []).find(p => p.platform_id === selectedPlatform.platform_id);
        if (pd) pd.scheduled_time = null;
        renderFields();
        toast('تم إزالة الموعد', 'success');
    } catch (e) {
        toast(e.message || 'فشل الإزالة', 'error');
    }
}

function updateConfirmState() {
    const fields = platformFields[selectedPlatform.platform_id] || [];
    const requiredFields = fields.filter(f => f.is_required && f.is_copyable);
    const pd = (currentTopic.platform_data || []).find(p => p.platform_id === selectedPlatform.platform_id);
    let values = {};
    try { values = JSON.parse(pd?.field_values || '{}'); } catch (e) {}

    const requiredWithValues = requiredFields.filter(f => {
        const v = values[f.field_name];
        return v && (Array.isArray(v) ? v.length > 0 : v.toString().trim() !== '');
    });

    const copied = requiredWithValues.filter(f => copiedFields.has(f.field_name)).length;
    const total = requiredWithValues.length;

    const progressEl = document.getElementById('confirm-progress');
    const btnEl = document.getElementById('confirm-btn');

    if (total === 0) {
        progressEl.textContent = '';
        btnEl.disabled = false;
    } else {
        progressEl.textContent = `تم نسخ ${copied} من ${total} حقول إجبارية`;
        btnEl.disabled = copied < total;

        // All required fields copied → show forced confirm modal
        if (copied >= total && !forcedConfirmPending) {
            showForcedConfirm();
        }
    }
}

// ===== Forced Confirmation =====
function showForcedConfirm() {
    if (!currentTopic || !selectedPlatform) return;
    forcedConfirmPending = true;
    const topicTitle = currentTopic.title || '#' + currentTopic.topic_number;
    const plName = selectedPlatform.display_name;
    document.getElementById('forced-confirm-body').textContent =
        `هل تم رفع "${topicTitle}" على ${plName}؟`;
    document.getElementById('forced-confirm-modal').classList.remove('hidden');
    // Enable beforeunload warning
    window.addEventListener('beforeunload', beforeUnloadWarning);
}

function closeForcedConfirm() {
    document.getElementById('forced-confirm-modal').classList.add('hidden');
    forcedConfirmPending = false;
    window.removeEventListener('beforeunload', beforeUnloadWarning);
}

function beforeUnloadWarning(e) {
    e.preventDefault();
    e.returnValue = 'فيه موضوع لم يتم تأكيد رفعه — هل متأكد إنك عايز تغادر؟';
    return e.returnValue;
}

function onForcedConfirmClick() {
    closeForcedConfirm();
    doConfirmUpload();
}

// ===== Manual Confirmation (button click) =====
function onConfirmClick() {
    const plName = selectedPlatform.display_name;
    const topicTitle = currentTopic.title || '#' + currentTopic.topic_number;

    showModal(
        'تأكيد الرفع',
        `هل تم رفع "${topicTitle}" على ${plName}؟`,
        doConfirmUpload
    );
}

async function doConfirmUpload() {
    try {
        await api('POST', `/api/topics/${currentTopic.id}/platforms/${selectedPlatform.platform_id}/confirm`, {
            employee_id: currentUser.employee_id,
        });
        closeForcedConfirm();
        toast('تم تأكيد الرفع بنجاح', 'success');

        // Go back to topic list
        showTopics();
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
        const result = await api('POST', `/api/tiktok/upload/${currentTopic.id}/${selectedPlatform.platform_id}`, {
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

function escapeAttr(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

// ===== Init =====
(async function init() {
    const saved = localStorage.getItem('user');
    if (saved) {
        try {
            const parsed = JSON.parse(saved);
            if (parsed && parsed.employee_id && parsed.name) {
                try {
                    const emp = await api('GET', `/api/employees/${parsed.employee_id}`);
                    if (emp && emp.is_active) {
                        currentUser = parsed;
                        goToChannels();
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
