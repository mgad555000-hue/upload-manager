/* Upload Manager — Admin Panel Logic */

const API = '';
let currentUser = null;
let channels = [];
let platforms = [];
let platformFields = {};
let employees = [];
let scheduleRules = [];

// ===== API Helper =====
async function api(method, path, body) {
    const opts = { method, headers: { 'Content-Type': 'application/json; charset=utf-8' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(API + path, opts);
    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'خطأ في السيرفر');
    }
    if (res.status === 204) return {};
    return res.json();
}

// ===== Toast =====
function toast(msg, type = '') {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.className = 'toast show ' + type;
    setTimeout(() => el.className = 'toast', 2500);
}

// ===== Escape HTML =====
function esc(s) {
    if (s === null || s === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(s);
    return div.innerHTML.replace(/"/g, '&quot;');
}

// ===== PIN Login =====
let pin = '';

function pinInput(n) {
    if (pin.length >= 4) return;
    pin += n;
    updatePinDots();
    if (pin.length === 4) setTimeout(doLogin, 200);
}

function pinDelete() {
    pin = pin.slice(0, -1);
    updatePinDots();
    document.getElementById('login-error').textContent = '';
}

function updatePinDots() {
    for (let i = 0; i < 4; i++) {
        const dot = document.getElementById('dot-' + i);
        if (i < pin.length) { dot.textContent = '\u25CF'; dot.classList.add('filled'); }
        else { dot.textContent = ''; dot.classList.remove('filled'); }
    }
}

async function doLogin() {
    try {
        const data = await api('POST', '/api/auth/login', { pin });
        if (data.role !== 'admin') {
            document.getElementById('login-error').textContent = 'الدخول للأدمن فقط';
            pin = ''; updatePinDots();
            return;
        }
        currentUser = data;
        localStorage.setItem('admin_user', JSON.stringify(data));
        showAdmin();
    } catch (e) {
        document.getElementById('login-error').textContent = e.message;
        pin = ''; updatePinDots();
    }
}

function logout() {
    currentUser = null;
    localStorage.removeItem('admin_user');
    pin = ''; updatePinDots();
    document.getElementById('admin-panel').classList.add('hidden');
    document.getElementById('login-screen').style.display = '';
}

// ===== Init =====
(function init() {
    const saved = localStorage.getItem('admin_user');
    if (saved) {
        try {
            const parsed = JSON.parse(saved);
            if (parsed && parsed.employee_id && parsed.role === 'admin') {
                currentUser = parsed;
                showAdmin();
                return;
            }
            localStorage.removeItem('admin_user');
        } catch (e) { localStorage.removeItem('admin_user'); }
    }
})();

// ===== Show Admin =====
async function showAdmin() {
    document.getElementById('login-screen').style.display = 'none';
    document.getElementById('admin-panel').classList.remove('hidden');
    document.getElementById('user-name').textContent = currentUser.name;
    try {
        await loadAllData();
        renderChannels();
    } catch (e) {
        toast('فشل تحميل البيانات', 'error');
    }
}

async function loadAllData() {
    try {
        [channels, platforms, employees, scheduleRules] = await Promise.all([
            api('GET', '/api/channels?include_inactive=true'),
            api('GET', '/api/platforms?include_inactive=true'),
            api('GET', '/api/employees'),
            api('GET', '/api/schedule'),
        ]);
        // Load fields for each platform
        for (const p of platforms) {
            platformFields[p.id] = await api('GET', `/api/platforms/${p.id}/fields`);
        }
    } catch (e) {
        toast('فشل تحميل البيانات', 'error');
    }
}

// ===== Section Navigation =====
let activeSection = 'channels';

function showSection(name, btn) {
    activeSection = name;
    document.querySelectorAll('.admin-section').forEach(s => s.classList.remove('active'));
    const sec = document.getElementById('sec-' + name);
    if (sec) sec.classList.add('active');
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');

    if (name === 'channels') renderChannels();
    else if (name === 'platforms') renderPlatforms();
    else if (name === 'employees') renderEmployees();
    else if (name === 'schedule') renderSchedule();
    else if (name === 'youtube') renderYouTube();
    else if (name === 'import') renderImport();
    else if (name === 'mg-ranner') renderMGRanner();
    else if (name === 'logs') renderLogs();
}

// ===== Form Modal =====
function openForm(title, html, onSave) {
    const modal = document.getElementById('form-modal');
    modal.innerHTML = `
        <div class="form-content">
            <h3>${esc(title)}</h3>
            ${html}
            <div class="form-actions">
                <button class="btn-cancel" onclick="closeForm()">إلغاء</button>
                <button class="btn-save" id="form-save-btn">حفظ</button>
            </div>
        </div>`;
    modal.classList.remove('hidden');
    document.getElementById('form-save-btn').onclick = async function () {
        if (this.disabled) return;
        this.disabled = true;
        try {
            await onSave();
            closeForm();
        } catch (e) {
            toast(e.message, 'error');
            this.disabled = false;
        }
    };
}

function closeForm() {
    document.getElementById('form-modal').classList.add('hidden');
}

function formVal(id) {
    const el = document.getElementById(id);
    if (!el) return '';
    if (el.type === 'checkbox') return el.checked;
    return el.value;
}

// ===== CHANNELS =====
function renderChannels() {
    let html = `<button class="btn-add" onclick="addChannel()">+ إضافة قناة</button>`;
    for (const ch of channels) {
        html += `
        <div class="admin-card">
            <div class="card-header">
                <div>
                    <div class="card-title">${esc(ch.display_name || ch.name)}</div>
                    <div class="card-subtitle">${esc(ch.name)}</div>
                </div>
                <div class="card-actions">
                    <span class="status-badge ${ch.is_active ? 'status-active' : 'status-inactive'}">${ch.is_active ? 'مفعّل' : 'معطّل'}</span>
                    <button class="btn-sm btn-edit" onclick="editChannel(${ch.id})">تعديل</button>
                </div>
            </div>
            <div class="card-meta">
                ${ch.youtube_channel_id ? 'YouTube: ' + esc(ch.youtube_channel_id) : ''}
                ${ch.default_hashtags ? ' | هاشتاجات: ' + esc(ch.default_hashtags) : ''}
            </div>
        </div>`;
    }
    document.getElementById('sec-channels').innerHTML = html;
}

function addChannel() {
    openForm('إضافة قناة', `
        <div class="form-group"><label>الاسم (إنجليزي)</label><input id="f-name" placeholder="My_Channel"></div>
        <div class="form-group"><label>اسم العرض (عربي)</label><input id="f-display" placeholder="قناتي"></div>
        <div class="form-group"><label>YouTube Channel ID</label><input id="f-ytid" dir="ltr"></div>
        <div class="form-group"><label>Facebook Page ID</label><input id="f-fbid" dir="ltr"></div>
        <div class="form-group"><label>الهاشتاجات الافتراضية</label><input id="f-hashtags" placeholder="#tag1 #tag2"></div>
        <div class="form-group"><label>الروابط الافتراضية</label><textarea id="f-links" placeholder="رابط لكل سطر"></textarea></div>
        <div class="form-group"><label>YouTube Category ID</label><input id="f-catid" type="number" dir="ltr"></div>
    `, async () => {
        const body = {
            name: formVal('f-name'),
            display_name: formVal('f-display') || null,
            youtube_channel_id: formVal('f-ytid') || null,
            facebook_page_id: formVal('f-fbid') || null,
            default_hashtags: formVal('f-hashtags') || null,
            default_links: formVal('f-links') || null,
            youtube_category_id: formVal('f-catid') ? parseInt(formVal('f-catid')) : null,
        };
        await api('POST', '/api/channels', body);
        toast('تمت الإضافة', 'success');
        await loadAllData();
        renderChannels();
    });
}

function editChannel(id) {
    const ch = channels.find(c => c.id === id);
    if (!ch) return;
    openForm('تعديل قناة: ' + (ch.display_name || ch.name), `
        <div class="form-group"><label>الاسم (إنجليزي)</label><input id="f-name" value="${esc(ch.name)}"></div>
        <div class="form-group"><label>اسم العرض (عربي)</label><input id="f-display" value="${esc(ch.display_name || '')}"></div>
        <div class="form-group"><label>YouTube Channel ID</label><input id="f-ytid" value="${esc(ch.youtube_channel_id || '')}" dir="ltr"></div>
        <div class="form-group"><label>Facebook Page ID</label><input id="f-fbid" value="${esc(ch.facebook_page_id || '')}" dir="ltr"></div>
        <div class="form-group"><label>الهاشتاجات الافتراضية</label><input id="f-hashtags" value="${esc(ch.default_hashtags || '')}"></div>
        <div class="form-group"><label>الروابط الافتراضية</label><textarea id="f-links">${esc(ch.default_links || '')}</textarea></div>
        <div class="form-group"><label>YouTube Category ID</label><input id="f-catid" type="number" value="${esc(ch.youtube_category_id || '')}" dir="ltr"></div>
        <div class="form-check"><input type="checkbox" id="f-active" ${ch.is_active ? 'checked' : ''}><label for="f-active">مفعّل</label></div>
    `, async () => {
        const body = {
            name: formVal('f-name'),
            display_name: formVal('f-display') || null,
            youtube_channel_id: formVal('f-ytid') || null,
            facebook_page_id: formVal('f-fbid') || null,
            default_hashtags: formVal('f-hashtags') || null,
            default_links: formVal('f-links') || null,
            youtube_category_id: formVal('f-catid') ? parseInt(formVal('f-catid')) : null,
            is_active: formVal('f-active'),
        };
        await api('PUT', `/api/channels/${id}`, body);
        toast('تم التحديث', 'success');
        await loadAllData();
        renderChannels();
    });
}

// ===== PLATFORMS =====
function renderPlatforms() {
    let html = '';
    for (const p of platforms) {
        const fields = platformFields[p.id] || [];
        let fieldsHtml = '';
        for (const f of fields) {
            fieldsHtml += `
            <div class="field-item">
                <div class="field-info">
                    <div class="field-name">${esc(f.field_label || f.field_name)}</div>
                    <div class="field-tags">
                        <span class="tag tag-type">${esc(f.field_type)}</span>
                        ${f.is_required ? '<span class="tag tag-required">مطلوب</span>' : ''}
                        ${f.is_copyable ? '<span class="tag tag-copyable">قابل للنسخ</span>' : '<span class="tag tag-hidden">مخفي النسخ</span>'}
                    </div>
                </div>
                <button class="btn-sm btn-edit" onclick="editField(${p.id}, ${f.id})">تعديل</button>
                <button class="btn-sm btn-delete" onclick="deleteField(${f.id}, '${esc(f.field_name).replace(/\\/g, '\\\\').replace(/'/g, "\\'")}')">حذف</button>
            </div>`;
        }

        html += `
        <div class="admin-card">
            <div class="card-header">
                <div>
                    <div class="card-title">${esc(p.display_name || p.name)}</div>
                    <div class="card-subtitle">
                        <span class="status-badge ${p.mode === 'auto' ? 'status-auto' : 'status-manual'}">${p.mode === 'auto' ? 'أوتوماتيك' : 'يدوي'}</span>
                    </div>
                </div>
                <div class="card-actions">
                    <span class="status-badge ${p.is_active ? 'status-active' : 'status-inactive'}">${p.is_active ? 'مفعّل' : 'معطّل'}</span>
                </div>
            </div>
            <div style="margin-top:10px">
                <div style="font-size:12px;color:var(--text2);margin-bottom:8px">الحقول (${fields.length})</div>
                ${fieldsHtml}
                <button class="btn-add" style="margin-top:8px;padding:8px;font-size:12px" onclick="addField(${p.id})">+ إضافة حقل</button>
            </div>
        </div>`;
    }
    document.getElementById('sec-platforms').innerHTML = html;
}

function addField(platformId) {
    const p = platforms.find(x => x.id === platformId);
    openForm('إضافة حقل — ' + (p ? (p.display_name || p.name) : ''), `
        <div class="form-group"><label>اسم الحقل (إنجليزي)</label><input id="f-name" placeholder="description" dir="ltr"></div>
        <div class="form-group"><label>عنوان العرض (عربي)</label><input id="f-label" placeholder="الوصف"></div>
        <div class="form-group"><label>النوع</label>
            <select id="f-type">
                <option value="text">نص قصير</option>
                <option value="textarea">نص طويل</option>
                <option value="tags">كلمات مفتاحية</option>
            </select>
        </div>
        <div class="form-group"><label>ترتيب العرض</label><input id="f-order" type="number" value="0" dir="ltr"></div>
        <div class="form-check"><input type="checkbox" id="f-required" checked><label for="f-required">مطلوب</label></div>
        <div class="form-check"><input type="checkbox" id="f-copyable" checked><label for="f-copyable">قابل للنسخ (يظهر زرار النسخ)</label></div>
    `, async () => {
        await api('POST', `/api/platforms/${platformId}/fields`, {
            field_name: formVal('f-name'),
            field_label: formVal('f-label') || null,
            field_type: formVal('f-type'),
            is_required: formVal('f-required'),
            is_copyable: formVal('f-copyable'),
            display_order: parseInt(formVal('f-order')) || 0,
        });
        toast('تمت الإضافة', 'success');
        await loadAllData();
        renderPlatforms();
    });
}

function editField(platformId, fieldId) {
    const fields = platformFields[platformId] || [];
    const f = fields.find(x => x.id === fieldId);
    if (!f) return;
    openForm('تعديل حقل: ' + (f.field_label || f.field_name), `
        <div class="form-group"><label>اسم الحقل (إنجليزي)</label><input id="f-name" value="${esc(f.field_name)}" dir="ltr"></div>
        <div class="form-group"><label>عنوان العرض (عربي)</label><input id="f-label" value="${esc(f.field_label || '')}"></div>
        <div class="form-group"><label>النوع</label>
            <select id="f-type">
                <option value="text" ${f.field_type === 'text' ? 'selected' : ''}>نص قصير</option>
                <option value="textarea" ${f.field_type === 'textarea' ? 'selected' : ''}>نص طويل</option>
                <option value="tags" ${f.field_type === 'tags' ? 'selected' : ''}>كلمات مفتاحية</option>
            </select>
        </div>
        <div class="form-group"><label>ترتيب العرض</label><input id="f-order" type="number" value="${esc(f.display_order)}" dir="ltr"></div>
        <div class="form-check"><input type="checkbox" id="f-required" ${f.is_required ? 'checked' : ''}><label for="f-required">مطلوب</label></div>
        <div class="form-check"><input type="checkbox" id="f-copyable" ${f.is_copyable ? 'checked' : ''}><label for="f-copyable">قابل للنسخ (يظهر زرار النسخ)</label></div>
    `, async () => {
        await api('PUT', `/api/platforms/fields/${fieldId}`, {
            field_name: formVal('f-name'),
            field_label: formVal('f-label') || null,
            field_type: formVal('f-type'),
            is_required: formVal('f-required'),
            is_copyable: formVal('f-copyable'),
            display_order: parseInt(formVal('f-order')) || 0,
        });
        toast('تم التحديث', 'success');
        await loadAllData();
        renderPlatforms();
    });
}

async function deleteField(fieldId, fieldName) {
    if (!confirm('حذف الحقل "' + fieldName + '"؟')) return;
    try {
        await api('DELETE', `/api/platforms/fields/${fieldId}`);
        toast('تم الحذف', 'success');
        await loadAllData();
        renderPlatforms();
    } catch (e) {
        toast(e.message, 'error');
    }
}

// ===== EMPLOYEES =====
function renderEmployees() {
    let html = `<button class="btn-add" onclick="addEmployee()">+ إضافة موظف</button>`;
    for (const emp of employees) {
        html += `
        <div class="admin-card">
            <div class="card-header">
                <div>
                    <div class="card-title">${esc(emp.name)}</div>
                    <div class="card-subtitle">
                        <span class="status-badge ${emp.role === 'admin' ? 'status-auto' : 'status-manual'}">${emp.role === 'admin' ? 'أدمن' : 'رافع'}</span>
                    </div>
                </div>
                <div class="card-actions">
                    <span class="status-badge ${emp.is_active ? 'status-active' : 'status-inactive'}">${emp.is_active ? 'مفعّل' : 'معطّل'}</span>
                    <button class="btn-sm btn-edit" onclick="editEmployee(${emp.id})">تعديل</button>
                </div>
            </div>
        </div>`;
    }
    document.getElementById('sec-employees').innerHTML = html;
}

function addEmployee() {
    openForm('إضافة موظف', `
        <div class="form-group"><label>الاسم</label><input id="f-name" placeholder="محمد"></div>
        <div class="form-group"><label>كود الدخول (PIN)</label><input id="f-pin" maxlength="4" placeholder="1234" dir="ltr"></div>
        <div class="form-group"><label>الصلاحية</label>
            <select id="f-role">
                <option value="uploader">رافع</option>
                <option value="admin">أدمن</option>
            </select>
        </div>
    `, async () => {
        await api('POST', '/api/employees', {
            name: formVal('f-name'),
            pin: formVal('f-pin'),
            role: formVal('f-role'),
        });
        toast('تمت الإضافة', 'success');
        await loadAllData();
        renderEmployees();
    });
}

function editEmployee(id) {
    const emp = employees.find(e => e.id === id);
    if (!emp) return;
    openForm('تعديل موظف: ' + emp.name, `
        <div class="form-group"><label>الاسم</label><input id="f-name" value="${esc(emp.name)}"></div>
        <div class="form-group"><label>كود جديد (اتركه فارغ لو مش عايز تغيره)</label><input id="f-pin" maxlength="4" dir="ltr"></div>
        <div class="form-group"><label>الصلاحية</label>
            <select id="f-role">
                <option value="uploader" ${emp.role === 'uploader' ? 'selected' : ''}>رافع</option>
                <option value="admin" ${emp.role === 'admin' ? 'selected' : ''}>أدمن</option>
            </select>
        </div>
        <div class="form-check"><input type="checkbox" id="f-active" ${emp.is_active ? 'checked' : ''}><label for="f-active">مفعّل</label></div>
    `, async () => {
        const body = {
            name: formVal('f-name'),
            role: formVal('f-role'),
            is_active: formVal('f-active'),
        };
        const pinVal = formVal('f-pin');
        if (pinVal) body.pin = pinVal;
        await api('PUT', `/api/employees/${id}`, body);
        toast('تم التحديث', 'success');
        await loadAllData();
        renderEmployees();
    });
}

// ===== SCHEDULE RULES =====
function renderSchedule() {
    let html = `<button class="btn-add" onclick="addScheduleRule()">+ إضافة قاعدة جدولة</button>`;
    for (const r of scheduleRules) {
        const ch = channels.find(c => c.id === r.channel_id);
        const pl = platforms.find(p => p.id === r.platform_id);
        let times = [];
        try { times = JSON.parse(r.publish_times); } catch (e) {}

        html += `
        <div class="admin-card">
            <div class="card-header">
                <div>
                    <div class="card-title">${esc(ch ? (ch.display_name || ch.name) : '?')} — ${esc(pl ? (pl.display_name || pl.name) : '?')}</div>
                    <div class="card-subtitle">${esc(r.content_type)} | ${esc(r.timezone)}</div>
                </div>
                <div class="card-actions">
                    <span class="status-badge ${r.is_active ? 'status-active' : 'status-inactive'}">${r.is_active ? 'مفعّل' : 'معطّل'}</span>
                    <button class="btn-sm btn-edit" onclick="editScheduleRule(${r.id})">تعديل</button>
                    <button class="btn-sm btn-delete" onclick="deleteScheduleRule(${r.id})">حذف</button>
                </div>
            </div>
            <div class="card-meta" style="margin-top:6px">
                المواعيد: ${times.map(t => '<span style="background:var(--surface2);padding:2px 8px;border-radius:4px;font-size:11px;margin-left:4px">' + esc(t) + '</span>').join(' ')}
            </div>
        </div>`;
    }
    document.getElementById('sec-schedule').innerHTML = html;
}

function _channelOptions(selectedId) {
    return channels.map(c => `<option value="${c.id}" ${c.id === selectedId ? 'selected' : ''}>${esc(c.display_name || c.name)}</option>`).join('');
}
function _platformOptions(selectedId) {
    return platforms.map(p => `<option value="${p.id}" ${p.id === selectedId ? 'selected' : ''}>${esc(p.display_name || p.name)}</option>`).join('');
}

function addScheduleRule() {
    openForm('إضافة قاعدة جدولة', `
        <div class="form-group"><label>القناة</label><select id="f-channel">${_channelOptions()}</select></div>
        <div class="form-group"><label>المنصة</label><select id="f-platform">${_platformOptions()}</select></div>
        <div class="form-group"><label>نوع المحتوى</label>
            <select id="f-content"><option value="shorts">Shorts</option><option value="long">Long</option></select>
        </div>
        <div class="form-group"><label>مواعيد النشر (وقت لكل سطر)</label><textarea id="f-times" placeholder="08:00\n10:00\n12:00" dir="ltr" style="font-family:monospace"></textarea></div>
        <div class="form-group"><label>المنطقة الزمنية</label><input id="f-tz" value="Africa/Cairo" dir="ltr"></div>
    `, async () => {
        const times = formVal('f-times').split('\n').map(t => t.trim()).filter(Boolean);
        await api('POST', '/api/schedule', {
            channel_id: parseInt(formVal('f-channel')),
            platform_id: parseInt(formVal('f-platform')),
            content_type: formVal('f-content'),
            publish_times: JSON.stringify(times),
            timezone: formVal('f-tz'),
        });
        toast('تمت الإضافة', 'success');
        await loadAllData();
        renderSchedule();
    });
}

function editScheduleRule(id) {
    const r = scheduleRules.find(x => x.id === id);
    if (!r) return;
    let times = [];
    try { times = JSON.parse(r.publish_times); } catch (e) {}

    openForm('تعديل قاعدة جدولة', `
        <div class="form-group"><label>مواعيد النشر (وقت لكل سطر)</label><textarea id="f-times" dir="ltr" style="font-family:monospace">${esc(times.join('\n'))}</textarea></div>
        <div class="form-group"><label>نوع المحتوى</label>
            <select id="f-content">
                <option value="shorts" ${r.content_type === 'shorts' ? 'selected' : ''}>Shorts</option>
                <option value="long" ${r.content_type === 'long' ? 'selected' : ''}>Long</option>
            </select>
        </div>
        <div class="form-check"><input type="checkbox" id="f-active" ${r.is_active ? 'checked' : ''}><label for="f-active">مفعّل</label></div>
    `, async () => {
        const times = formVal('f-times').split('\n').map(t => t.trim()).filter(Boolean);
        await api('PUT', `/api/schedule/${id}`, {
            publish_times: JSON.stringify(times),
            content_type: formVal('f-content'),
            is_active: formVal('f-active'),
        });
        toast('تم التحديث', 'success');
        await loadAllData();
        renderSchedule();
    });
}

async function deleteScheduleRule(id) {
    if (!confirm('حذف قاعدة الجدولة دي؟')) return;
    try {
        await api('DELETE', `/api/schedule/${id}`);
        toast('تم الحذف', 'success');
        await loadAllData();
        renderSchedule();
    } catch (e) { toast(e.message, 'error'); }
}

// ===== LOGS =====
async function renderLogs() {
    const container = document.getElementById('sec-logs');
    container.innerHTML = '<div class="loading">جاري التحميل...</div>';
    try {
        const logs = await api('GET', '/api/logs?limit=100');
        if (logs.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>مفيش سجلات</p></div>';
            return;
        }
        let html = '';
        for (const log of logs) {
            const emp = employees.find(e => e.id === log.employee_id);
            const empName = emp ? emp.name : (log.employee_id || '—');
            const pl = platforms.find(p => p.id === log.platform_id);
            const plName = pl ? (pl.display_name || pl.name) : '';
            let details = '';
            try {
                const d = JSON.parse(log.details || '{}');
                if (d.field) details = 'حقل: ' + d.field;
                else if (d.reason) details = 'سبب: ' + d.reason;
            } catch (e) {}

            const actionLabels = {
                'lock': 'قفل', 'unlock': 'فك', 'confirm_upload': 'تأكيد رفع',
                'copy_field': 'نسخ حقل', 'auto_unlock': 'فك تلقائي'
            };

            html += `
            <div class="log-item">
                <div>
                    <div class="log-action">${esc(actionLabels[log.action] || log.action)} ${plName ? '— ' + esc(plName) : ''}</div>
                    <div class="log-details">${esc(empName)} ${details ? '| ' + esc(details) : ''} ${log.topic_id ? '| موضوع #' + esc(log.topic_id) : ''}</div>
                </div>
                <div class="log-time">${formatTime(log.created_at)}</div>
            </div>`;
        }
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<div class="empty-state"><p>فشل تحميل السجلات</p></div>';
    }
}

function formatTime(dt) {
    if (!dt) return '';
    const d = new Date(dt);
    const h = d.getHours();
    const m = d.getMinutes().toString().padStart(2, '0');
    const day = d.getDate();
    const month = d.getMonth() + 1;
    return `${day}/${month} ${h}:${m}`;
}

// ===== YOUTUBE =====
async function renderYouTube() {
    const container = document.getElementById('sec-youtube');
    container.innerHTML = '<div class="loading">جاري التحميل...</div>';
    try {
        const statuses = await api('GET', '/api/youtube/status');
        let html = '<div style="font-size:13px;color:var(--text2);margin-bottom:12px">ربط قنوات YouTube — OAuth2 + رفع أوتوماتيك + كوتا</div>';

        // Fix: fetch quotas in parallel instead of sequentially
        const quotaResults = {};
        const connectedChannels = statuses.filter(s => s.has_token);
        if (connectedChannels.length > 0) {
            const quotaPromises = connectedChannels.map(s =>
                api('GET', `/api/youtube/quota/${s.channel_id}`)
                    .then(q => { quotaResults[s.channel_id] = q; })
                    .catch(() => {})
            );
            await Promise.all(quotaPromises);
        }

        for (const s of statuses) {
            let quotaHtml = '';
            let checkHtml = '';
            if (s.has_token) {
                const q = quotaResults[s.channel_id];
                if (q) {
                    // Fix: use parseFloat instead of esc() for CSS numeric value
                    const pct = q.daily_limit > 0 ? Math.min(100, parseFloat((q.units_used / q.daily_limit) * 100)) : 0;
                    quotaHtml = `
                        <div style="margin-top:10px">
                            <div class="yt-quota-bar"><div class="yt-quota-fill" style="width:${pct}%"></div></div>
                            <div class="yt-quota-text">${esc(q.units_used)} / ${esc(q.daily_limit)} وحدة — متبقي ${esc(q.uploads_remaining)} رفع</div>
                        </div>`;
                }

                checkHtml = `
                    <button class="btn-sm btn-edit" onclick="ytCheck(this, ${s.channel_id})">فحص</button>
                    <button class="btn-sm btn-yt-disconnect" onclick="ytDisconnect(this, ${s.channel_id}, '${esc(s.channel_name).replace(/\\/g, '\\\\').replace(/'/g, "\\'")}')">فصل</button>`;
            } else {
                checkHtml = `<button class="btn-sm btn-yt-connect" onclick="ytConnect(this, ${s.channel_id})">ربط YouTube</button>`;
            }

            html += `
            <div class="yt-card">
                <div class="yt-header">
                    <div>
                        <div class="yt-channel">${esc(s.channel_name)}</div>
                        <div style="font-size:12px;margin-top:4px" class="${s.has_token ? 'yt-connected' : 'yt-disconnected'}">
                            ${s.has_token ? '● مربوط' : '○ غير مربوط'}
                            ${s.youtube_channel_title ? ' — ' + esc(s.youtube_channel_title) : ''}
                        </div>
                    </div>
                    <div class="card-actions">${checkHtml}</div>
                </div>
                ${quotaHtml}
            </div>`;
        }

        if (statuses.length === 0) {
            html += '<div class="empty-state"><p>مفيش قنوات — أضف قناة الأول</p></div>';
        }

        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<div class="empty-state"><p>فشل تحميل بيانات YouTube</p></div>';
    }
}

// Fix: all YouTube buttons receive `btn` and disable during async
async function ytConnect(btn, channelId) {
    if (btn.disabled) return;
    btn.disabled = true;
    try {
        const data = await api('GET', `/api/youtube/auth-url/${channelId}`);
        if (data.auth_url) {
            window.open(data.auth_url, '_blank');
            toast('اتفتحت صفحة تسجيل الدخول في تاب جديد', 'success');
        }
    } catch (e) {
        toast(e.message, 'error');
    } finally {
        btn.disabled = false;
    }
}

async function ytCheck(btn, channelId) {
    if (btn.disabled) return;
    btn.disabled = true;
    try {
        const result = await api('POST', `/api/youtube/check/${channelId}`);
        if (result.valid) {
            toast('التوكن شغال — ' + (result.youtube_channel_title || ''), 'success');
        } else {
            toast('التوكن باظ — ' + (result.error || 'اربط القناة تاني'), 'error');
        }
        await renderYouTube();
    } catch (e) {
        toast(e.message, 'error');
        btn.disabled = false;
    }
}

async function ytDisconnect(btn, channelId, name) {
    if (btn.disabled) return;
    if (!confirm('فصل "' + name + '" من YouTube؟')) return;
    btn.disabled = true;
    try {
        await api('DELETE', `/api/youtube/disconnect/${channelId}`);
        toast('تم الفصل', 'success');
        await renderYouTube();
    } catch (e) {
        toast(e.message, 'error');
        btn.disabled = false;
    }
}

// ===== WORD IMPORT =====
function renderImport() {
    const container = document.getElementById('sec-import');
    let channelOpts = channels.map(c =>
        `<option value="${c.id}">${esc(c.display_name || c.name)}</option>`
    ).join('');

    container.innerHTML = `
        <div style="font-size:13px;color:var(--text2);margin-bottom:12px">
            استيراد مواضيع من ملف Word — جدول واحد بالعناوين الصحيحة
        </div>
        <a class="btn-template" href="/api/import/template" download="import_template.docx">
            تحميل القالب الفارغ
        </a>
        <div class="import-form">
            <div class="form-group">
                <label>القناة</label>
                <select id="import-channel">${channelOpts}</select>
            </div>
            <div class="form-group">
                <label>نوع المحتوى</label>
                <select id="import-type">
                    <option value="shorts">Shorts</option>
                    <option value="long">Long</option>
                </select>
            </div>
            <div class="form-group">
                <label>ملف Word (.docx)</label>
                <input type="file" id="import-file" accept=".docx">
            </div>
            <div class="form-group">
                <label>بداية الجدولة من تاريخ (اختياري)</label>
                <input type="date" id="import-schedule-start" dir="ltr" style="cursor:pointer;padding:8px 12px;font-size:14px;min-height:40px" onclick="this.showPicker&&this.showPicker()">
                <div style="font-size:11px;color:var(--text2);margin-top:4px">لو فاضي → الجدولة تبدأ من أقرب وقت فاضي</div>
            </div>
            <button class="btn-import" id="import-btn" onclick="doImport()" disabled>استيراد</button>
        </div>
        <div id="import-result"></div>`;

    // Enable button when file selected
    document.getElementById('import-file').onchange = function() {
        document.getElementById('import-btn').disabled = !this.files.length;
    };
}

async function doImport() {
    const btn = document.getElementById('import-btn');
    if (btn.disabled) return;
    btn.disabled = true;
    btn.textContent = 'جاري الاستيراد...';

    const fileInput = document.getElementById('import-file');
    const channelId = document.getElementById('import-channel').value;
    const contentType = document.getElementById('import-type').value;

    if (!fileInput.files.length) {
        toast('اختار ملف الأول', 'error');
        btn.disabled = false;
        btn.textContent = 'استيراد';
        return;
    }

    const scheduleStart = document.getElementById('import-schedule-start').value || '';
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('channel_id', channelId);
    formData.append('content_type', contentType);
    if (scheduleStart) formData.append('schedule_start_from', scheduleStart);

    try {
        const res = await fetch('/api/import/word', {
            method: 'POST',
            body: formData,
        });
        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.detail || 'خطأ في الاستيراد');
        }

        let html = `<div class="import-result">`;
        html += `<div class="result-success">تم استيراد ${esc(data.created)} من ${esc(data.total)} موضوع</div>`;

        if (data.parse_errors && data.parse_errors.length > 0) {
            html += `<div style="margin-top:8px;font-size:12px;color:var(--warning)">أخطاء التحليل:</div>`;
            for (const e of data.parse_errors) {
                html += `<div class="result-error">${esc(e)}</div>`;
            }
        }
        if (data.create_errors && data.create_errors.length > 0) {
            html += `<div style="margin-top:8px;font-size:12px;color:var(--danger)">أخطاء الإنشاء:</div>`;
            for (const e of data.create_errors) {
                html += `<div class="result-error">${esc(e)}</div>`;
            }
        }
        html += `</div>`;
        document.getElementById('import-result').innerHTML = html;

        if (data.created > 0) {
            toast(`تم استيراد ${data.created} موضوع`, 'success');
        }
    } catch (e) {
        toast(e.message, 'error');
        document.getElementById('import-result').innerHTML =
            `<div class="import-result"><div class="result-error">${esc(e.message)}</div></div>`;
    } finally {
        btn.disabled = false;
        btn.textContent = 'استيراد';
    }
}

// ===== MG RANNER IMPORT =====
let mgParsedTopics = [];

const MG_FIELD_LABELS = {
    yt_title_1: 'عنوان يوتيوب 1',
    yt_title_2: 'عنوان يوتيوب 2',
    yt_desc_1: 'وصف يوتيوب 1',
    yt_desc_2: 'وصف يوتيوب 2',
    yt_thumb_1: 'صورة مصغرة يوتيوب 1',
    yt_thumb_2: 'صورة مصغرة يوتيوب 2',
    yt_keywords: 'كلمات مفتاحية يوتيوب',
    tt_title: 'عنوان تيك توك',
    tt_desc: 'وصف تيك توك',
    tt_screen: 'جملة شاشة تيك توك',
    fb_title: 'عنوان فيسبوك',
    fb_desc: 'وصف فيسبوك',
    fb_thumb: 'صورة مصغرة فيسبوك',
    fb_keywords: 'كلمات مفتاحية فيسبوك',
    tr_en_title: 'عنوان إنجليزي',
    tr_en_desc: 'وصف إنجليزي',
    tr_fr_title: 'عنوان فرنسي',
    tr_fr_desc: 'وصف فرنسي',
    tr_es_title: 'عنوان إسباني',
    tr_es_desc: 'وصف إسباني',
    tr_de_title: 'عنوان ألماني',
    tr_de_desc: 'وصف ألماني',
};

// Default mapping: platform field -> source mg field
const MG_DEFAULT_MAP = {
    youtube: {
        title: 'yt_title_1',
        description: 'yt_desc_1',
        tags: 'yt_keywords',
        thumbnail_text: 'yt_thumb_1',
    },
    tiktok: {
        description: 'tt_desc',
        hashtags: 'tt_desc',
        screen_text: 'tt_screen',
    },
    facebook: {
        title: 'fb_title',
        description: 'fb_desc',
    },
};

function renderMGRanner() {
    const container = document.getElementById('sec-mg-ranner');
    let channelOpts = channels.map(c =>
        `<option value="${c.id}">${esc(c.display_name || c.name)}</option>`
    ).join('');

    container.innerHTML = `
        <div style="font-size:13px;color:var(--text2);margin-bottom:12px">
            استيراد مواضيع من ملف MG Ranner — scripts_output.docx
        </div>
        <div class="import-form">
            <div class="form-group">
                <label>القناة</label>
                <select id="mg-channel">${channelOpts}</select>
            </div>
            <div class="form-group">
                <label>نوع المحتوى</label>
                <select id="mg-type">
                    <option value="shorts">Shorts</option>
                    <option value="long" selected>Long</option>
                </select>
            </div>
            <div class="form-group">
                <label>ملف Word (.docx)</label>
                <input type="file" id="mg-file" accept=".docx">
            </div>
            <div class="form-group">
                <label>مجلد الفيديوهات (اختياري)</label>
                <input type="text" id="mg-video-folder" placeholder="C:\\path\\to\\videos" dir="ltr">
            </div>
            <div class="form-group">
                <label>بداية الجدولة من تاريخ (اختياري)</label>
                <input type="date" id="mg-schedule-start" dir="ltr" style="cursor:pointer;padding:8px 12px;font-size:14px;min-height:40px" onclick="this.showPicker&&this.showPicker()">
                <div style="font-size:11px;color:var(--text2);margin-top:4px">لو فاضي → الجدولة تبدأ من أقرب وقت فاضي</div>
            </div>
            <button class="btn-import" id="mg-parse-btn" onclick="parseMGRanner()" disabled>تحليل الملف</button>
        </div>
        <div id="mg-results"></div>`;

    document.getElementById('mg-file').onchange = function() {
        document.getElementById('mg-parse-btn').disabled = !this.files.length;
    };
}

async function parseMGRanner() {
    const btn = document.getElementById('mg-parse-btn');
    if (btn.disabled) return;
    btn.disabled = true;
    btn.textContent = 'جاري التحليل...';

    const fileInput = document.getElementById('mg-file');
    if (!fileInput.files.length) {
        toast('اختار ملف الأول', 'error');
        btn.disabled = false;
        btn.textContent = 'تحليل الملف';
        return;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    try {
        const res = await fetch('/api/import/mg-ranner-parse', {
            method: 'POST',
            body: formData,
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'خطأ في التحليل');

        mgParsedTopics = data.topics || [];
        const channelId = parseInt(document.getElementById('mg-channel').value);
        const contentType = document.getElementById('mg-type').value;

        if (data.errors && data.errors.length > 0) {
            let errHtml = '<div style="margin-bottom:12px">';
            for (const e of data.errors) {
                errHtml += `<div style="color:var(--warning);font-size:12px;margin-bottom:4px">${esc(e)}</div>`;
            }
            errHtml += '</div>';
            document.getElementById('mg-results').innerHTML = errHtml;
        }

        if (mgParsedTopics.length > 0) {
            toast(`تم تحليل ${mgParsedTopics.length} موضوع`, 'success');
            renderMGCards(mgParsedTopics, channelId, contentType);
        } else {
            document.getElementById('mg-results').innerHTML =
                '<div class="empty-state"><p>مفيش مواضيع في الملف</p></div>';
        }
    } catch (e) {
        toast(e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'تحليل الملف';
    }
}

function renderMGCards(topics, channelId, contentType) {
    const container = document.getElementById('mg-results');
    const fieldKeys = Object.keys(MG_FIELD_LABELS);

    // Build source options HTML once
    function sourceOptions(selectedKey, topicFields) {
        let opts = '<option value="">-- اختر --</option>';
        for (const fk of fieldKeys) {
            if (topicFields[fk]) {
                const sel = fk === selectedKey ? ' selected' : '';
                opts += `<option value="${esc(fk)}"${sel}>${esc(MG_FIELD_LABELS[fk])}</option>`;
            }
        }
        return opts;
    }

    // Platform configs for display
    const platformConfigs = [
        {
            name: 'youtube',
            label: 'يوتيوب',
            fields: [
                { field: 'title', label: 'العنوان' },
                { field: 'description', label: 'الوصف' },
                { field: 'tags', label: 'الكلمات المفتاحية' },
                { field: 'thumbnail_text', label: 'جملة الصورة المصغرة' },
            ],
        },
        {
            name: 'tiktok',
            label: 'تيك توك',
            fields: [
                { field: 'description', label: 'الوصف' },
                { field: 'hashtags', label: 'الهاشتاجات' },
                { field: 'screen_text', label: 'جملة الشاشة' },
            ],
        },
        {
            name: 'facebook',
            label: 'فيسبوك',
            fields: [
                { field: 'title', label: 'العنوان' },
                { field: 'description', label: 'الوصف' },
            ],
        },
    ];

    let html = `<div style="margin:12px 0;font-size:13px;color:var(--text2)">
        تم تحليل <strong>${topics.length}</strong> موضوع — راجع وعدّل وبعدين اضغط ابعت
    </div>`;

    for (let ti = 0; ti < topics.length; ti++) {
        const t = topics[ti];
        const fields = t.fields;

        html += `<div class="mg-card" id="mg-card-${ti}">`;
        html += `<div class="mg-card-header">
            <div style="display:flex;align-items:center;gap:8px">
                <input type="checkbox" class="mg-include" data-idx="${ti}" checked
                    onchange="document.getElementById('mg-card-${ti}').classList.toggle('excluded', !this.checked)">
                <strong>Script ${esc(t.topic_number)}</strong>
            </div>
            <span style="font-size:11px;color:var(--text2)">${Object.keys(fields).length} حقل</span>
        </div>`;

        for (const pc of platformConfigs) {
            html += `<div class="mg-platform-section">
                <div class="mg-platform-title">${esc(pc.label)}</div>`;

            for (const pf of pc.fields) {
                const defaultSrc = (MG_DEFAULT_MAP[pc.name] || {})[pf.field] || '';
                const defaultValue = fields[defaultSrc] || '';
                const selectId = `mg-sel-${ti}-${pc.name}-${pf.field}`;
                const textId = `mg-txt-${ti}-${pc.name}-${pf.field}`;

                html += `<div class="mg-field-row">
                    <label>${esc(pf.label)}</label>
                    <select class="mg-field-source" id="${selectId}"
                        onchange="mgFieldChanged(${ti}, '${pc.name}', '${pf.field}')">
                        ${sourceOptions(defaultSrc, fields)}
                    </select>
                    <textarea class="mg-field-text" id="${textId}" rows="2">${esc(defaultValue)}</textarea>
                </div>`;
            }
            html += '</div>';
        }
        html += '</div>';
    }

    html += `<div class="mg-submit-bar">
        <button class="btn-import" onclick="submitMGTopics()" style="max-width:400px;margin:0 auto">
            ابعت الكل لـ Upload Manager
        </button>
    </div>`;

    container.innerHTML += html;
}

function mgFieldChanged(topicIdx, platformName, fieldName) {
    const selId = `mg-sel-${topicIdx}-${platformName}-${fieldName}`;
    const txtId = `mg-txt-${topicIdx}-${platformName}-${fieldName}`;
    const sel = document.getElementById(selId);
    const txt = document.getElementById(txtId);
    if (!sel || !txt) return;

    const srcKey = sel.value;
    if (srcKey && mgParsedTopics[topicIdx]) {
        txt.value = mgParsedTopics[topicIdx].fields[srcKey] || '';
    }
}

async function submitMGTopics() {
    const channelId = parseInt(document.getElementById('mg-channel').value);
    const contentType = document.getElementById('mg-type').value;
    const videoFolder = document.getElementById('mg-video-folder').value.trim();

    // Get platform IDs from loaded platforms data
    const platformIds = {};
    for (const p of platforms) {
        platformIds[p.name] = p.id;
    }

    const platformConfigs = [
        { name: 'youtube', fields: ['title', 'description', 'tags', 'thumbnail_text'] },
        { name: 'tiktok', fields: ['description', 'hashtags', 'screen_text'] },
        { name: 'facebook', fields: ['title', 'description'] },
    ];

    const topicsToSend = [];

    for (let ti = 0; ti < mgParsedTopics.length; ti++) {
        const checkbox = document.querySelector(`#mg-card-${ti} .mg-include`);
        if (!checkbox || !checkbox.checked) continue;

        const t = mgParsedTopics[ti];
        const platformData = [];

        for (const pc of platformConfigs) {
            const pid = platformIds[pc.name];
            if (!pid) continue;

            const fieldValues = {};
            for (const fn of pc.fields) {
                const txtId = `mg-txt-${ti}-${pc.name}-${fn}`;
                const txt = document.getElementById(txtId);
                if (txt && txt.value.trim()) {
                    fieldValues[fn] = txt.value.trim();
                }
            }

            if (Object.keys(fieldValues).length > 0) {
                platformData.push({
                    platform_id: pid,
                    field_values: fieldValues,
                });
            }
        }

        const topicObj = {
            channel_id: channelId,
            topic_number: t.topic_number,
            content_type: contentType,
            title: t.fields.yt_title_1 || t.fields.fb_title || t.fields.tt_title || '',
            platform_data: platformData,
        };

        if (videoFolder) {
            topicObj.video_path = videoFolder;
        }

        topicsToSend.push(topicObj);
    }

    if (topicsToSend.length === 0) {
        toast('مفيش مواضيع محددة للإرسال', 'error');
        return;
    }

    try {
        const scheduleStart = document.getElementById('mg-schedule-start').value || null;
        const payload = { topics: topicsToSend };
        if (scheduleStart) payload.schedule_start_from = scheduleStart;
        const result = await api('POST', '/api/topics/batch', payload);
        const created = typeof result.created === 'number' ? result.created : (Array.isArray(result.created) ? result.created.length : 0);
        const errs = result.errors || [];

        if (created > 0) {
            toast(`تم إنشاء ${created} موضوع بنجاح`, 'success');
        }
        if (errs.length > 0) {
            toast(`${errs.length} أخطاء أثناء الإنشاء`, 'error');
        }

        // Show result summary
        let summaryHtml = `<div class="import-result" style="margin-top:12px">`;
        summaryHtml += `<div class="result-success">تم إنشاء ${created} من ${topicsToSend.length} موضوع</div>`;
        if (errs.length > 0) {
            summaryHtml += `<div style="margin-top:8px;font-size:12px;color:var(--danger)">أخطاء:</div>`;
            for (const e of errs) {
                summaryHtml += `<div class="result-error">${esc(e)}</div>`;
            }
        }
        summaryHtml += '</div>';
        document.getElementById('mg-results').innerHTML = summaryHtml;

    } catch (e) {
        toast(e.message, 'error');
    }
}

// Fix: Check for YouTube auth callback — navigate to YouTube tab after login
(function checkYouTubeCallback() {
    const params = new URLSearchParams(window.location.search);
    if (params.get('youtube_auth') === 'success') {
        window.history.replaceState({}, '', window.location.pathname);
        // Wait for login to complete, then switch to YouTube tab
        const waitForAdmin = setInterval(() => {
            if (currentUser) {
                clearInterval(waitForAdmin);
                const ytBtn = document.querySelector('.nav-btn:nth-child(5)');
                showSection('youtube', ytBtn);
                toast('تم ربط القناة بيوتيوب بنجاح!', 'success');
            }
        }, 300);
        // Timeout after 10s
        setTimeout(() => clearInterval(waitForAdmin), 10000);
    }
})();
