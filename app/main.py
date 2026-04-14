"""
Upload Manager — FastAPI Backend
نظام إدارة رفع الفيديوهات على منصات التواصل الاجتماعي
"""
import sys
if sys.stdout:
    sys.stdout.reconfigure(encoding='utf-8')

from fastapi import FastAPI, Depends, HTTPException, Query, File, UploadFile, Form, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError as SQLIntegrityError
from typing import List, Optional
from contextlib import asynccontextmanager
import os
import json
import asyncio
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

from fastapi.responses import RedirectResponse

from app.database import (
    get_db, init_db, Channel, Platform, PlatformField, Topic,
    PlatformData, Employee, UploadLog, ScheduleRule,
    OAuthToken, QuotaUsage, AuthToken,
)
from app.models import (
    ChannelCreate, ChannelUpdate, ChannelResponse,
    PlatformResponse, PlatformFieldCreate, PlatformFieldUpdate, PlatformFieldResponse,
    TopicCreate, TopicUpdate, TopicResponse, TopicBatchCreate, PlatformDataInput, PlatformDataResponse,
    EmployeeCreate, EmployeeUpdate, EmployeeResponse, LoginRequest, LoginResponse,
    UploadConfirm, CopyLogRequest, UploadLogResponse,
    ScheduleRuleCreate, ScheduleRuleUpdate, ScheduleRuleResponse, RescheduleRequest,
    DashboardStats,
    YouTubeAuthStatus, YouTubeUploadRequest, YouTubeUploadResponse, QuotaStatusResponse,
    WordImportResponse, TikTokUploadRequest, TikTokUploadResponse,
)

import hashlib
import secrets

STATIC_DIR = os.getenv("STATIC_DIR", "./static")
Path(STATIC_DIR).mkdir(parents=True, exist_ok=True)

# ========== Auth Helpers ==========

def _hash_pin(pin: str) -> str:
    """Hash PIN with SHA-256 + salt stored in the hash itself"""
    salt = secrets.token_hex(8)
    h = hashlib.sha256(f"{salt}:{pin}".encode()).hexdigest()
    return f"{salt}:{h}"

def _verify_pin(pin: str, stored: str) -> bool:
    """Verify PIN against stored hash. Also accepts plain text for migration."""
    if ":" in stored and len(stored) > 20:
        # Hashed format: salt:hash
        salt, h = stored.split(":", 1)
        return hashlib.sha256(f"{salt}:{pin}".encode()).hexdigest() == h
    else:
        # Plain text (legacy) — matches for migration
        return pin == stored

def _generate_token(employee_id: int) -> str:
    """Generate a secure random token"""
    return f"{employee_id}:{secrets.token_hex(16)}"

def _save_token(db: Session, token: str, employee_id: int):
    """Save token to database for persistence across restarts"""
    db.add(AuthToken(token=token, employee_id=employee_id))
    db.commit()

def _validate_token_db(db: Session, token: str) -> int | None:
    """Returns employee_id if token is valid (from DB), else None"""
    auth = db.query(AuthToken).filter(AuthToken.token == token).first()
    return auth.employee_id if auth else None

def require_auth(authorization: str = Header(None), db: Session = Depends(get_db)) -> Employee:
    """Dependency: require valid token, return Employee object"""
    if not authorization:
        raise HTTPException(401, "مطلوب تسجيل دخول")
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    emp_id = _validate_token_db(db, token)
    if emp_id is None:
        raise HTTPException(401, "التوكن غير صالح — سجل دخول من جديد")
    emp = db.query(Employee).filter(Employee.id == emp_id, Employee.is_active == True).first()
    if not emp:
        raise HTTPException(401, "الموظف متعطل أو محذوف")
    return emp

def require_admin(emp: Employee = Depends(require_auth)) -> Employee:
    """Dependency: require admin role"""
    if emp.role != "admin":
        raise HTTPException(403, "مطلوب صلاحية أدمن")
    return emp


async def lock_cleanup_task():
    """Background task: فك الأقفال المنتهية (> 30 دقيقة) كل 5 دقايق"""
    from app.database import SessionLocal
    while True:
        await asyncio.sleep(300)  # 5 minutes
        db = None
        try:
            db = SessionLocal()
            lock_cutoff = datetime.utcnow() - timedelta(minutes=10)
            upload_cutoff = datetime.utcnow() - timedelta(minutes=60)  # uploads stuck >1hr
            from sqlalchemy import update, or_
            # Release expired locks
            stmt_locked = (
                update(PlatformData)
                .where(
                    PlatformData.upload_status == "locked",
                    or_(
                        PlatformData.lock_time == None,
                        PlatformData.lock_time < lock_cutoff,
                    ),
                )
                .values(upload_status="pending", lock_holder=None, lock_time=None)
            )
            r1 = db.execute(stmt_locked)
            # Recovery: release uploads stuck >60 min (server crashed mid-upload)
            stmt_stuck = (
                update(PlatformData)
                .where(
                    PlatformData.upload_status == "uploading",
                    or_(
                        PlatformData.lock_time == None,
                        PlatformData.lock_time < upload_cutoff,
                    ),
                )
                .values(upload_status="pending", lock_holder=None, lock_time=None)
            )
            r2 = db.execute(stmt_stuck)
            total = r1.rowcount + r2.rowcount
            if total > 0:
                db.commit()
                if r1.rowcount: print(f"[Lock Cleanup] Released {r1.rowcount} expired locks")
                if r2.rowcount: print(f"[Lock Cleanup] Recovered {r2.rowcount} stuck uploads")
        except Exception as e:
            if db:
                db.rollback()
            print(f"[Lock Cleanup] Error: {e}")
        finally:
            if db:
                db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print("[Upload Manager] Started on port 8003")
    task = asyncio.create_task(lock_cleanup_task())
    yield
    task.cancel()


app = FastAPI(title="Upload Manager", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ========== Root ==========

@app.get("/")
async def root():
    index = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"message": "Upload Manager API", "version": "1.0.0", "docs": "/docs"}

@app.get("/admin")
async def admin_page():
    admin = os.path.join(STATIC_DIR, "admin.html")
    if os.path.exists(admin):
        return FileResponse(admin)
    return {"message": "Admin panel not yet built"}


# ========== Auth ==========

@app.post("/api/auth/login", response_model=LoginResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    # Try all active employees — support both hashed and plain PINs
    employees = db.query(Employee).filter(Employee.is_active == True).all()
    emp = None
    for e in employees:
        if _verify_pin(req.pin, e.pin):
            emp = e
            break
    if not emp:
        raise HTTPException(status_code=401, detail="PIN غير صحيح")
    # Migrate plain PIN to hashed on successful login
    if ":" not in emp.pin or len(emp.pin) <= 20:
        emp.pin = _hash_pin(req.pin)
        db.commit()
    token = _generate_token(emp.id)
    _save_token(db, token, emp.id)
    return LoginResponse(employee_id=emp.id, name=emp.name, role=emp.role, token=token)


# ========== Channels ==========

@app.get("/api/channels", response_model=List[ChannelResponse])
def list_channels(include_inactive: bool = False, db: Session = Depends(get_db)):
    q = db.query(Channel)
    if not include_inactive:
        q = q.filter(Channel.is_active == True)
    return q.all()

@app.post("/api/channels", response_model=ChannelResponse)
def create_channel(ch: ChannelCreate, db: Session = Depends(get_db), _admin: Employee = Depends(require_admin)):
    obj = Channel(**ch.model_dump())
    db.add(obj)
    try:
        db.commit()
    except SQLIntegrityError:
        db.rollback()
        raise HTTPException(409, f"القناة '{ch.name}' موجودة بالفعل")
    db.refresh(obj)
    return obj

@app.get("/api/channels/{channel_id}", response_model=ChannelResponse)
def get_channel(channel_id: int, db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "القناة مش موجودة")
    return ch

@app.put("/api/channels/{channel_id}", response_model=ChannelResponse)
def update_channel(channel_id: int, data: ChannelUpdate, db: Session = Depends(get_db), _admin: Employee = Depends(require_admin)):
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "القناة مش موجودة")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(ch, k, v)
    ch.updated_at = datetime.utcnow()
    try:
        db.commit()
    except SQLIntegrityError:
        db.rollback()
        raise HTTPException(409, f"الاسم '{data.model_dump(exclude_unset=True).get('name', '')}' موجود بالفعل")
    db.refresh(ch)
    return ch


# ========== Platforms ==========

@app.get("/api/platforms", response_model=List[PlatformResponse])
def list_platforms(include_inactive: bool = False, db: Session = Depends(get_db)):
    q = db.query(Platform)
    if not include_inactive:
        q = q.filter(Platform.is_active == True)
    return q.all()

@app.get("/api/platforms/{platform_id}/fields", response_model=List[PlatformFieldResponse])
def list_platform_fields(platform_id: int, db: Session = Depends(get_db)):
    return db.query(PlatformField).filter(
        PlatformField.platform_id == platform_id
    ).order_by(PlatformField.display_order).all()

@app.post("/api/platforms/{platform_id}/fields", response_model=PlatformFieldResponse)
def create_field(platform_id: int, f: PlatformFieldCreate, db: Session = Depends(get_db), _admin: Employee = Depends(require_admin)):
    plat = db.query(Platform).filter(Platform.id == platform_id).first()
    if not plat:
        raise HTTPException(404, "المنصة مش موجودة")
    obj = PlatformField(platform_id=platform_id, **f.model_dump())
    db.add(obj)
    try:
        db.commit()
    except SQLIntegrityError:
        db.rollback()
        raise HTTPException(409, "الحقل ده موجود بالفعل أو المنصة مش موجودة")
    db.refresh(obj)
    return obj

@app.put("/api/platforms/fields/{field_id}", response_model=PlatformFieldResponse)
def update_field(field_id: int, data: PlatformFieldUpdate, db: Session = Depends(get_db), _admin: Employee = Depends(require_admin)):
    f = db.query(PlatformField).filter(PlatformField.id == field_id).first()
    if not f:
        raise HTTPException(404, "الحقل مش موجود")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(f, k, v)
    db.commit()
    db.refresh(f)
    return f

@app.delete("/api/platforms/fields/{field_id}")
def delete_field(field_id: int, db: Session = Depends(get_db), _admin: Employee = Depends(require_admin)):
    f = db.query(PlatformField).filter(PlatformField.id == field_id).first()
    if not f:
        raise HTTPException(404, "الحقل مش موجود")
    db.delete(f)
    db.commit()
    return {"ok": True}


# ========== Topics ==========

@app.get("/api/topics", response_model=List[TopicResponse])
def list_topics(
    channel_id: Optional[int] = None,
    platform_id: Optional[int] = None,
    status: Optional[str] = None,
    content_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(Topic)
    if channel_id:
        q = q.filter(Topic.channel_id == channel_id)
    if platform_id:
        # Filter topics that have a platform_data entry for this platform
        q = q.filter(Topic.id.in_(
            db.query(PlatformData.topic_id).filter(PlatformData.platform_id == platform_id)
        ))
    if status:
        q = q.filter(Topic.status == status)
    if content_type:
        q = q.filter(Topic.content_type == content_type)
    topics = q.order_by(Topic.priority, Topic.id).offset(offset).limit(limit).all()
    # Load platform_data for each topic
    result = []
    for t in topics:
        resp = TopicResponse.model_validate(t)
        resp.platform_data = [PlatformDataResponse.model_validate(pd) for pd in t.platform_data]
        result.append(resp)
    return result

@app.post("/api/topics", response_model=TopicResponse)
def create_topic(data: TopicCreate, db: Session = Depends(get_db), target_platform_ids: list | None = None):
    # Check channel exists
    ch = db.query(Channel).filter(Channel.id == data.channel_id).first()
    if not ch:
        raise HTTPException(404, "القناة مش موجودة")

    topic = Topic(
        channel_id=data.channel_id,
        topic_number=data.topic_number,
        content_type=data.content_type,
        title=data.title,
        thumbnail_path=data.thumbnail_path,
        video_path=data.video_path,
        batch_number=data.batch_number,
        priority=data.priority or 0,
    )
    db.add(topic)
    try:
        db.flush()
    except SQLIntegrityError:
        db.rollback()
        raise HTTPException(409, f"الموضوع #{data.topic_number} ({data.content_type}) موجود بالفعل في القناة دي")

    # Create platform_data rows
    if data.platform_data:
        seen_platforms = set()
        for pd in data.platform_data:
            if pd.platform_id in seen_platforms:
                continue  # Skip duplicate platform in same request
            # Validate platform exists
            plat = db.query(Platform).filter(Platform.id == pd.platform_id).first()
            if not plat:
                db.rollback()
                raise HTTPException(404, f"المنصة {pd.platform_id} مش موجودة")
            seen_platforms.add(pd.platform_id)
            obj = PlatformData(
                topic_id=topic.id,
                platform_id=pd.platform_id,
                field_values=json.dumps(pd.field_values, ensure_ascii=False),
                scheduled_time=pd.scheduled_time,
            )
            db.add(obj)
    else:
        # Auto-create for selected platforms (or all active if not specified)
        if target_platform_ids:
            platforms = db.query(Platform).filter(Platform.id.in_(target_platform_ids), Platform.is_active == True).all()
        else:
            platforms = db.query(Platform).filter(Platform.is_active == True).all()
        for pl in platforms:
            db.add(PlatformData(
                topic_id=topic.id,
                platform_id=pl.id,
                field_values="{}",
            ))

    try:
        db.commit()
    except SQLIntegrityError:
        db.rollback()
        raise HTTPException(409, "بيانات المنصة مكررة")

    db.refresh(topic)
    resp = TopicResponse.model_validate(topic)
    resp.platform_data = [PlatformDataResponse.model_validate(pd) for pd in topic.platform_data]
    return resp

@app.post("/api/topics/batch")
def create_topics_batch(data: TopicBatchCreate, db: Session = Depends(get_db)):
    created = []
    errors = []
    from app.database import SessionLocal
    for i, t in enumerate(data.topics):
        topic_db = SessionLocal()
        try:
            result = create_topic(t, topic_db)
            created.append(result)
        except HTTPException as e:
            errors.append(f"topic {i}: {e.detail}")
        except SQLIntegrityError:
            errors.append(f"topic {i}: duplicate")
        except Exception:
            errors.append(f"topic {i}: خطأ غير متو��ع")
        finally:
            topic_db.close()
    return {"created": len(created), "total": len(data.topics), "errors": errors}

@app.get("/api/topics/{topic_id}", response_model=TopicResponse)
def get_topic(topic_id: int, db: Session = Depends(get_db)):
    t = db.query(Topic).filter(Topic.id == topic_id).first()
    if not t:
        raise HTTPException(404, "الموضوع مش موجود")
    resp = TopicResponse.model_validate(t)
    resp.platform_data = [PlatformDataResponse.model_validate(pd) for pd in t.platform_data]
    return resp

@app.put("/api/topics/{topic_id}", response_model=TopicResponse)
def update_topic(topic_id: int, data: TopicUpdate, db: Session = Depends(get_db)):
    t = db.query(Topic).filter(Topic.id == topic_id).first()
    if not t:
        raise HTTPException(404, "الموضوع مش موجود")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(t, k, v)
    t.updated_at = datetime.utcnow()
    try:
        db.commit()
    except SQLIntegrityError:
        db.rollback()
        raise HTTPException(409, "الموضوع ده موجود بالفعل بنفس الرقم والنوع في القناة دي")
    db.refresh(t)
    resp = TopicResponse.model_validate(t)
    resp.platform_data = [PlatformDataResponse.model_validate(pd) for pd in t.platform_data]
    return resp

@app.delete("/api/topics/{topic_id}")
def delete_topic(topic_id: int, db: Session = Depends(get_db), _admin: Employee = Depends(require_admin)):
    t = db.query(Topic).filter(Topic.id == topic_id).first()
    if not t:
        raise HTTPException(404, "الموضوع مش موجود")
    # Block deletion if any platform is currently uploading
    uploading = db.query(PlatformData).filter(
        PlatformData.topic_id == topic_id,
        PlatformData.upload_status == "uploading",
    ).count()
    if uploading > 0:
        raise HTTPException(409, f"مينفعش تمسح — فيه {uploading} منصة بيترفع عليها حالياً")
    db.delete(t)
    db.commit()
    return {"ok": True}


# ========== Platform Data ==========

@app.get("/api/topics/{topic_id}/platforms", response_model=List[PlatformDataResponse])
def get_topic_platforms(topic_id: int, db: Session = Depends(get_db)):
    t = db.query(Topic).filter(Topic.id == topic_id).first()
    if not t:
        raise HTTPException(404, "الموضوع مش موجود")
    return db.query(PlatformData).filter(PlatformData.topic_id == topic_id).all()

@app.put("/api/topics/{topic_id}/platforms/{platform_id}", response_model=PlatformDataResponse)
def update_platform_data(topic_id: int, platform_id: int, data: PlatformDataInput, db: Session = Depends(get_db)):
    pd = db.query(PlatformData).filter(
        PlatformData.topic_id == topic_id,
        PlatformData.platform_id == platform_id,
    ).first()
    if not pd:
        raise HTTPException(404, "بيانات المنصة مش موجودة")
    if pd.upload_status == "uploaded":
        raise HTTPException(400, "المنصة دي اترفعت بالفعل — مينفعش تتعدل")
    if pd.upload_status == "uploading":
        raise HTTPException(400, "الفيديو بيترفع حالياً — مينفعش تتعدل")
    # locked status doesn't block editing — only uploading is blocked
    pd.field_values = json.dumps(data.field_values, ensure_ascii=False)
    if data.scheduled_time is not None:
        pd.scheduled_time = data.scheduled_time
    pd.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(pd)
    return pd


@app.patch("/api/topics/{topic_id}/platforms/{platform_id}/schedule")
def update_schedule_time(topic_id: int, platform_id: int, body: dict, db: Session = Depends(get_db), _admin: Employee = Depends(require_admin)):
    """تعديل موعد النشر لمنصة معينة"""
    pd_rec = db.query(PlatformData).filter(
        PlatformData.topic_id == topic_id,
        PlatformData.platform_id == platform_id,
    ).first()
    if not pd_rec:
        raise HTTPException(404, "بيانات المنصة مش موجودة")
    if pd_rec.upload_status == "uploaded":
        raise HTTPException(400, "المنصة دي اترفعت بالفعل")
    raw = body.get("scheduled_time")
    if raw:
        try:
            pd_rec.scheduled_time = datetime.fromisoformat(str(raw))
        except ValueError:
            raise HTTPException(400, "تنسيق التاريخ غلط")
    else:
        pd_rec.scheduled_time = None
    pd_rec.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(pd_rec)
    return PlatformDataResponse.model_validate(pd_rec)


# ========== Upload (Lock / Confirm) ==========

@app.post("/api/topics/{topic_id}/platforms/{platform_id}/lock")
def lock_topic(topic_id: int, platform_id: int, req: UploadConfirm, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == req.employee_id).first()
    if not emp:
        raise HTTPException(404, "الموظف مش موجود")
    if not emp.is_active:
        raise HTTPException(403, "الموظف ده معطّل")
    pd = db.query(PlatformData).filter(
        PlatformData.topic_id == topic_id,
        PlatformData.platform_id == platform_id,
    ).first()
    if not pd:
        raise HTTPException(404, "مش موجود")
    if pd.upload_status == "uploaded":
        raise HTTPException(400, "الفيديو ده اترفع بالفعل على المنصة دي")
    if pd.upload_status == "uploading":
        raise HTTPException(400, "الفيديو بيترفع حالياً — مينفعش تقفل")
    # Atomic UPDATE to prevent race condition between concurrent lock requests
    from datetime import timedelta
    from sqlalchemy import update, or_, and_
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=10)  # Match lock_cleanup_task timeout
    old_holder = pd.lock_holder  # Save for auto_unlock log
    stmt = (
        update(PlatformData)
        .where(
            PlatformData.topic_id == topic_id,
            PlatformData.platform_id == platform_id,
            PlatformData.upload_status.notin_(["uploaded", "uploading"]),
            or_(
                PlatformData.upload_status == "pending",
                and_(
                    PlatformData.upload_status == "locked",
                    PlatformData.lock_holder == req.employee_id,
                ),
                and_(
                    PlatformData.upload_status == "locked",
                    or_(
                        PlatformData.lock_time == None,
                        PlatformData.lock_time < cutoff,
                    ),
                ),
            ),
        )
        .values(upload_status="locked", lock_holder=req.employee_id, lock_time=now)
    )
    result = db.execute(stmt)
    if result.rowcount == 0:
        # Re-read to give accurate error
        db.refresh(pd)
        if pd.upload_status == "uploaded":
            raise HTTPException(400, "الفيديو ده اترفع بالفعل على المنصة دي")
        if pd.upload_status == "uploading":
            raise HTTPException(400, "الفيديو بيترفع حالياً — مينفعش تقفل")
        raise HTTPException(400, "مقفول بواسطة موظف تاني")
    # Log expired lock takeover if applicable
    if old_holder and old_holder != req.employee_id:
        db.add(UploadLog(topic_id=topic_id, platform_id=platform_id,
                         employee_id=old_holder, action="auto_unlock",
                         details=json.dumps({"reason": "expired_takeover"})))
    db.add(UploadLog(topic_id=topic_id, platform_id=platform_id, employee_id=req.employee_id, action="lock"))
    db.commit()
    return {"ok": True, "status": "locked"}

@app.post("/api/topics/{topic_id}/platforms/{platform_id}/unlock")
def unlock_topic(topic_id: int, platform_id: int, req: UploadConfirm, db: Session = Depends(get_db)):
    emp_check = db.query(Employee).filter(Employee.id == req.employee_id).first()
    if not emp_check:
        raise HTTPException(404, "الموظف مش موجود")
    if not emp_check.is_active:
        raise HTTPException(403, "الموظف ده معطّل")
    pd = db.query(PlatformData).filter(
        PlatformData.topic_id == topic_id,
        PlatformData.platform_id == platform_id,
    ).first()
    if not pd:
        raise HTTPException(404, "مش موجود")
    if pd.upload_status == "uploaded":
        raise HTTPException(400, "المنصة دي اترفعت بالفعل — مينفعش تتفك")
    if pd.upload_status == "uploading":
        raise HTTPException(400, "الفيديو بيترفع حالياً — مينفعش تفك القفل")
    if pd.upload_status == "pending":
        raise HTTPException(400, "المنصة مش مقفولة أصلاً")
    # Check owner or admin
    if pd.lock_holder and pd.lock_holder != req.employee_id:
        emp = db.query(Employee).filter(Employee.id == req.employee_id).first()
        if not emp or emp.role != "admin":
            raise HTTPException(403, "مش مسموح — القفل ده لموظف تاني")
    pd.upload_status = "pending"
    pd.lock_holder = None
    pd.lock_time = None
    db.add(UploadLog(topic_id=topic_id, platform_id=platform_id, employee_id=req.employee_id, action="unlock"))
    db.commit()
    return {"ok": True, "status": "pending"}


# ========== Helper Functions ==========

def _cross_post(db: Session, topic_id: int, source_platform_id: int):
    """نسخ القيم المشتركة من المنصة المرفوعة للمنصات التانية في نفس الموضوع"""
    try:
        source_pd = db.query(PlatformData).filter(
            PlatformData.topic_id == topic_id,
            PlatformData.platform_id == source_platform_id,
        ).first()
        if not source_pd or not source_pd.field_values:
            return
        source_vals = json.loads(source_pd.field_values or "{}")
        if not source_vals:
            return

        # جيب كل المنصات التانية في نفس الموضوع
        other_pds = db.query(PlatformData).filter(
            PlatformData.topic_id == topic_id,
            PlatformData.platform_id != source_platform_id,
        ).all()

        for target_pd in other_pds:
            # بس لو لسه pending (مش مقفولة أو مرفوعة)
            if target_pd.upload_status != "pending":
                continue

            # جيب أسماء الحقول بتاعت المنصة الهدف
            target_fields = db.query(PlatformField).filter(
                PlatformField.platform_id == target_pd.platform_id,
            ).all()
            target_field_names = {f.field_name for f in target_fields}

            # القيم الحالية للمنصة الهدف
            target_vals = json.loads(target_pd.field_values or "{}")

            # انسخ القيم المشتركة (بس لو الحقل فاضي في الهدف)
            updated = False
            for key, val in source_vals.items():
                if key in target_field_names and not target_vals.get(key):
                    target_vals[key] = val
                    updated = True

            if updated:
                target_pd.field_values = json.dumps(target_vals, ensure_ascii=False)
    except Exception as e:
        print(f"[Cross-Post] Error: {e}")  # Log but don't fail


def _telegram_upload_failure(db: Session, topic, platform_id: int, error: str, employee_id: int):
    """إرسال إشعار فشل رفع عبر تليجرام"""
    try:
        from app.telegram import notify_upload_failure, is_configured
        if not is_configured():
            return
        channel = db.query(Channel).filter(Channel.id == topic.channel_id).first()
        platform = db.query(Platform).filter(Platform.id == platform_id).first()
        emp = db.query(Employee).filter(Employee.id == employee_id).first()
        notify_upload_failure(
            channel_name=channel.display_name or channel.name if channel else "",
            topic_number=topic.topic_number,
            platform_name=platform.display_name or platform.name if platform else "",
            error=error,
            employee_name=emp.name if emp else "",
        )
    except Exception:
        pass  # Telegram failure is not critical


@app.post("/api/topics/{topic_id}/platforms/{platform_id}/confirm")
def confirm_upload(topic_id: int, platform_id: int, req: UploadConfirm, db: Session = Depends(get_db)):
    emp_check = db.query(Employee).filter(Employee.id == req.employee_id).first()
    if not emp_check:
        raise HTTPException(404, "الموظف مش موجود")
    if not emp_check.is_active:
        raise HTTPException(403, "الموظف ده معطّل")
    pd = db.query(PlatformData).filter(
        PlatformData.topic_id == topic_id,
        PlatformData.platform_id == platform_id,
    ).first()
    if not pd:
        raise HTTPException(404, "مش موجود")
    if pd.upload_status == "uploaded":
        raise HTTPException(400, "اترفع بالفعل")
    if pd.upload_status == "uploading":
        raise HTTPException(400, "الفيديو بيترفع حالياً — استنى يخلص")
    if pd.upload_status == "pending":
        raise HTTPException(400, "لازم تقفل الموضوع الأول قبل التأكيد")
    # Check owner (status must be "locked" at this point)
    if pd.lock_holder and pd.lock_holder != req.employee_id:
        emp = db.query(Employee).filter(Employee.id == req.employee_id).first()
        if not emp or emp.role != "admin":
            raise HTTPException(403, "مش مسموح — لازم تكون انت اللي قافل")
    pd.upload_status = "uploaded"
    pd.uploaded_by = req.employee_id
    pd.uploaded_at = datetime.utcnow()
    pd.lock_holder = None
    pd.lock_time = None
    db.add(UploadLog(topic_id=topic_id, platform_id=platform_id, employee_id=req.employee_id, action="confirm_upload"))

    # Update topic status
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if topic:
        all_pd = db.query(PlatformData).filter(PlatformData.topic_id == topic_id).all()
        all_uploaded = all(p.upload_status == "uploaded" for p in all_pd)
        topic.status = "completed" if all_uploaded else "partial"

    # Cross-post: نسخ البيانات للمنصات التانية
    _cross_post(db, topic_id, platform_id)

    db.commit()

    # Telegram notification
    try:
        from app.telegram import notify_upload_success, is_configured
        if is_configured() and topic:
            platform = db.query(Platform).filter(Platform.id == platform_id).first()
            channel = db.query(Channel).filter(Channel.id == topic.channel_id).first()
            field_vals = json.loads(pd.field_values or "{}")
            notify_upload_success(
                channel_name=channel.display_name or channel.name if channel else "",
                topic_number=topic.topic_number,
                platform_name=platform.display_name or platform.name if platform else "",
                title=field_vals.get("title", topic.title or ""),
                employee_name=emp_check.name,
            )
    except Exception:
        pass  # Telegram failure is not critical

    return {"ok": True, "status": "uploaded"}

@app.post("/api/topics/{topic_id}/platforms/{platform_id}/revert-upload")
def revert_upload(topic_id: int, platform_id: int, db: Session = Depends(get_db), _admin: Employee = Depends(require_admin)):
    """إرجاع حالة المنصة من 'uploaded' لـ 'pending' — أدمن فقط"""
    pd = db.query(PlatformData).filter(
        PlatformData.topic_id == topic_id,
        PlatformData.platform_id == platform_id,
    ).first()
    if not pd:
        raise HTTPException(404, "بيانات المنصة مش موجودة")
    if pd.upload_status != "uploaded":
        raise HTTPException(400, "المنصة دي مش مرفوعة أصلاً")
    pd.upload_status = "pending"
    pd.uploaded_by = None
    pd.uploaded_at = None
    pd.lock_holder = None
    pd.lock_time = None
    # Update topic status
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if topic:
        topic.status = "pending"
        # Check if any other platform is still uploaded → partial
        other_uploaded = db.query(PlatformData).filter(
            PlatformData.topic_id == topic_id,
            PlatformData.platform_id != platform_id,
            PlatformData.upload_status == "uploaded",
        ).count()
        if other_uploaded > 0:
            topic.status = "partial"
    db.add(UploadLog(
        topic_id=topic_id, platform_id=platform_id, employee_id=_admin.id,
        action="revert_upload",
        details=json.dumps({"reason": "admin_revert"}, ensure_ascii=False),
    ))
    db.commit()
    return {"ok": True, "status": "pending"}


@app.post("/api/topics/{topic_id}/platforms/{platform_id}/copy-log")
def log_copy(topic_id: int, platform_id: int, req: CopyLogRequest, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == req.employee_id).first()
    if not emp:
        raise HTTPException(404, "الموظف مش موجود")
    if not emp.is_active:
        raise HTTPException(403, "الموظف ده معطّل")
    pd_check = db.query(PlatformData).filter(
        PlatformData.topic_id == topic_id,
        PlatformData.platform_id == platform_id,
    ).first()
    if not pd_check:
        raise HTTPException(404, "الموضوع أو المنصة مش موجودة")
    db.add(UploadLog(
        topic_id=topic_id, platform_id=platform_id, employee_id=req.employee_id,
        action="copy_field", details=json.dumps({"field": req.field_name}, ensure_ascii=False),
    ))
    db.commit()
    return {"ok": True}


# ========== Employees ==========

@app.get("/api/employees", response_model=List[EmployeeResponse])
def list_employees(db: Session = Depends(get_db)):
    return db.query(Employee).all()

@app.get("/api/employees/{emp_id}", response_model=EmployeeResponse)
def get_employee(emp_id: int, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(404, "الموظف مش موجود")
    return emp

@app.post("/api/employees", response_model=EmployeeResponse)
def create_employee(data: EmployeeCreate, db: Session = Depends(get_db), _admin: Employee = Depends(require_admin)):
    # Hash the PIN before storing
    data_dict = data.model_dump()
    data_dict["pin"] = _hash_pin(data_dict["pin"])
    obj = Employee(**data_dict)
    db.add(obj)
    try:
        db.commit()
    except SQLIntegrityError:
        db.rollback()
        raise HTTPException(409, "الموظف ده موجود بالفعل")
    db.refresh(obj)
    return obj

@app.put("/api/employees/{emp_id}", response_model=EmployeeResponse)
def update_employee(emp_id: int, data: EmployeeUpdate, db: Session = Depends(get_db), _admin: Employee = Depends(require_admin)):
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(404, "الموظف مش موجود")
    updates = data.model_dump(exclude_unset=True)
    # Prevent last admin from being downgraded or deactivated
    if emp.role == "admin":
        losing_admin = (updates.get("role") and updates["role"] != "admin") or (updates.get("is_active") is False)
        if losing_admin:
            admin_count = db.query(Employee).filter(Employee.role == "admin", Employee.is_active == True, Employee.id != emp_id).count()
            if admin_count == 0:
                raise HTTPException(400, "مينفعش — ده آخر أدمن في النظام")
    for k, v in updates.items():
        if k == "pin" and v:
            v = _hash_pin(v)
        setattr(emp, k, v)
    db.commit()
    db.refresh(emp)
    return emp


# ========== Schedule Rules ==========

@app.get("/api/schedule", response_model=List[ScheduleRuleResponse])
def list_schedule_rules(
    channel_id: Optional[int] = None,
    platform_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    q = db.query(ScheduleRule)
    if channel_id:
        q = q.filter(ScheduleRule.channel_id == channel_id)
    if platform_id:
        q = q.filter(ScheduleRule.platform_id == platform_id)
    return q.all()

@app.post("/api/schedule", response_model=ScheduleRuleResponse)
def create_schedule_rule(data: ScheduleRuleCreate, db: Session = Depends(get_db), _admin: Employee = Depends(require_admin)):
    ch = db.query(Channel).filter(Channel.id == data.channel_id).first()
    if not ch:
        raise HTTPException(404, "القناة مش موجودة")
    pl = db.query(Platform).filter(Platform.id == data.platform_id).first()
    if not pl:
        raise HTTPException(404, "المنصة مش موجودة")
    obj = ScheduleRule(**data.model_dump())
    db.add(obj)
    try:
        db.commit()
    except SQLIntegrityError:
        db.rollback()
        raise HTTPException(409, "القاعدة دي موجودة بالفعل")
    db.refresh(obj)
    return obj

@app.put("/api/schedule/{rule_id}", response_model=ScheduleRuleResponse)
def update_schedule_rule(rule_id: int, data: ScheduleRuleUpdate, db: Session = Depends(get_db), _admin: Employee = Depends(require_admin)):
    r = db.query(ScheduleRule).filter(ScheduleRule.id == rule_id).first()
    if not r:
        raise HTTPException(404, "القاعدة مش موجودة")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(r, k, v)
    db.commit()
    db.refresh(r)
    return r

@app.delete("/api/schedule/{rule_id}")
def delete_schedule_rule(rule_id: int, db: Session = Depends(get_db), _admin: Employee = Depends(require_admin)):
    r = db.query(ScheduleRule).filter(ScheduleRule.id == rule_id).first()
    if not r:
        raise HTTPException(404, "القاعدة مش موجودة")
    db.delete(r)
    db.commit()
    return {"ok": True}


@app.post("/api/schedule/reschedule")
def reschedule_videos(data: RescheduleRequest, db: Session = Depends(get_db), _admin: Employee = Depends(require_admin)):
    """
    تغيير موعد فيديو (فردي أو متتالي).
    cascade=true: يغيّر كل الفيديوهات اللي بعده بناءً على الجدولة
    """
    from app.scheduler import reschedule_from
    changed = reschedule_from(db, data.topic_id, data.platform_id, data.new_time, data.cascade)
    if changed == 0:
        raise HTTPException(404, "الفيديو مش موجود أو اترفع بالفعل")
    return {"ok": True, "changed": changed}


@app.get("/api/schedule/videos")
def list_scheduled_videos(
    channel_id: int,
    platform_id: int,
    content_type: str = "shorts",
    db: Session = Depends(get_db),
):
    """قائمة الفيديوهات المجدولة لقناة ومنصة معينة (مرتبة بالموعد)"""
    rows = db.query(PlatformData, Topic).join(
        PlatformData.topic
    ).filter(
        PlatformData.platform_id == platform_id,
        Topic.channel_id == channel_id,
        Topic.content_type == content_type,
    ).order_by(Topic.topic_number.asc()).all()

    result = []
    for pd, topic in rows:
        result.append({
            "topic_id": topic.id,
            "topic_number": topic.topic_number,
            "title": topic.title,
            "platform_id": pd.platform_id,
            "scheduled_time": pd.scheduled_time.isoformat() if pd.scheduled_time else None,
            "upload_status": pd.upload_status,
        })
    return result


# ========== Upload Log ==========

@app.get("/api/logs", response_model=List[UploadLogResponse])
def list_logs(
    topic_id: Optional[int] = None,
    employee_id: Optional[int] = None,
    action: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(UploadLog)
    if topic_id:
        q = q.filter(UploadLog.topic_id == topic_id)
    if employee_id:
        q = q.filter(UploadLog.employee_id == employee_id)
    if action:
        q = q.filter(UploadLog.action == action)
    return q.order_by(UploadLog.id.desc()).limit(limit).all()


# ========== Dashboard ==========

@app.get("/api/dashboard/stats", response_model=DashboardStats)
def dashboard_stats(
    channel_id: Optional[int] = None,
    platform_id: Optional[int] = None,
    content_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    # Use UTC for consistency with DB timestamps
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Build topic ID subquery (efficient — stays in DB, no Python list)
    topic_subq = db.query(Topic.id)
    if channel_id:
        topic_subq = topic_subq.filter(Topic.channel_id == channel_id)
    if content_type:
        topic_subq = topic_subq.filter(Topic.content_type == content_type)
    if platform_id:
        topic_subq = topic_subq.filter(Topic.id.in_(
            db.query(PlatformData.topic_id).filter(PlatformData.platform_id == platform_id)
        ))

    total = topic_subq.count()

    # Platform data query filtered by topic subquery
    pd_base = db.query(PlatformData).filter(
        PlatformData.topic_id.in_(topic_subq.subquery())
    )
    if platform_id:
        pd_base = pd_base.filter(PlatformData.platform_id == platform_id)

    pending = pd_base.filter(PlatformData.upload_status == "pending").count()
    uploaded_today = pd_base.filter(
        PlatformData.upload_status == "uploaded",
        PlatformData.uploaded_at >= today_start,
    ).count()
    locked = pd_base.filter(PlatformData.upload_status == "locked").count()

    return DashboardStats(
        total_topics=total,
        pending_uploads=pending,
        uploaded_today=uploaded_today,
        locked_now=locked,
    )


# ========== Navigation Counts ==========

@app.get("/api/nav/channel-counts")
def nav_channel_counts(db: Session = Depends(get_db)):
    """عدد المواضيع المعلقة لكل قناة"""
    channels_list = db.query(Channel).filter(Channel.is_active == True).all()
    result = []
    for ch in channels_list:
        pending = db.query(PlatformData).join(Topic).filter(
            Topic.channel_id == ch.id,
            PlatformData.upload_status.in_(["pending", "locked"]),
        ).count()
        total = db.query(Topic).filter(Topic.channel_id == ch.id).count()
        result.append({
            "channel_id": ch.id,
            "name": ch.name,
            "display_name": ch.display_name or ch.name,
            "pending": pending,
            "total": total,
        })
    return result

@app.get("/api/nav/platform-counts/{channel_id}")
def nav_platform_counts(channel_id: int, db: Session = Depends(get_db)):
    """عدد المواضيع المعلقة لكل منصة في قناة معينة"""
    platforms_list = db.query(Platform).filter(Platform.is_active == True).all()
    result = []
    for pl in platforms_list:
        pending = db.query(PlatformData).join(Topic).filter(
            Topic.channel_id == channel_id,
            PlatformData.platform_id == pl.id,
            PlatformData.upload_status.in_(["pending", "locked"]),
        ).count()
        total = db.query(PlatformData).join(Topic).filter(
            Topic.channel_id == channel_id,
            PlatformData.platform_id == pl.id,
        ).count()
        result.append({
            "platform_id": pl.id,
            "name": pl.name,
            "display_name": pl.display_name or pl.name,
            "mode": pl.mode,
            "pending": pending,
            "total": total,
        })
    return result

@app.get("/api/nav/content-counts/{channel_id}/{platform_id}")
def nav_content_counts(channel_id: int, platform_id: int, db: Session = Depends(get_db)):
    """عدد المواضيع المعلقة لكل نوع محتوى في قناة ومنصة معينة"""
    result = []
    for ct in ["shorts", "long"]:
        pending = db.query(PlatformData).join(Topic).filter(
            Topic.channel_id == channel_id,
            Topic.content_type == ct,
            PlatformData.platform_id == platform_id,
            PlatformData.upload_status.in_(["pending", "locked"]),
        ).count()
        total = db.query(PlatformData).join(Topic).filter(
            Topic.channel_id == channel_id,
            Topic.content_type == ct,
            PlatformData.platform_id == platform_id,
        ).count()
        result.append({
            "content_type": ct,
            "pending": pending,
            "total": total,
        })
    return result


# ========== Webhook (MG Ranner Integration) ==========

@app.post("/api/webhooks/mg-ranner")
def mg_ranner_webhook(data: TopicCreate, db: Session = Depends(get_db)):
    """shorts-runner يبلّغ لما ينتج موضوع جديد"""
    return create_topic(data, db)


# ========== YouTube API ==========

@app.get("/api/youtube/auth-url/{channel_id}")
def youtube_auth_url(channel_id: int, db: Session = Depends(get_db)):
    """توليد رابط OAuth2 لربط قناة يوتيوب"""
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "القناة مش موجودة")

    from app.youtube import get_auth_url
    redirect_uri = os.getenv("YOUTUBE_REDIRECT_URI", "http://localhost:8003/api/youtube/callback")
    url = get_auth_url(redirect_uri, channel_id)
    if not url:
        raise HTTPException(500, "YouTube credentials مش متظبطة — راجع YOUTUBE_CLIENT_ID و YOUTUBE_CLIENT_SECRET")
    return {"auth_url": url}


@app.get("/api/youtube/callback")
def youtube_callback(code: str, state: str, db: Session = Depends(get_db)):
    """OAuth2 callback — استقبال الكود وتخزين التوكن"""
    from app.youtube import exchange_code
    from urllib.parse import quote

    # Fix: wrap int() in try/except
    try:
        channel_id = int(state)
    except (ValueError, TypeError):
        raise HTTPException(400, "state parameter غلط")

    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "القناة مش موجودة")

    redirect_uri = os.getenv("YOUTUBE_REDIRECT_URI", "http://localhost:8003/api/youtube/callback")
    # Fix: wrap exchange_code in try/except for invalid/expired codes
    try:
        token_data = exchange_code(code, redirect_uri)
    except Exception:
        raise HTTPException(400, "كود التفويض غلط أو منتهي — جرب تاني")
    if not token_data:
        raise HTTPException(500, "فشل في تبادل الكود — راجع YouTube credentials")

    # Fix: handle None refresh_token
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        raise HTTPException(400, "Google مرجعش refresh token — امسح التطبيق من حساب جوجل وجرب تاني")

    # حفظ أو تحديث التوكن
    existing = db.query(OAuthToken).filter(OAuthToken.channel_id == channel_id).first()
    if existing:
        existing.access_token = token_data["access_token"]
        existing.refresh_token = refresh_token
        existing.token_expiry = datetime.fromisoformat(token_data["token_expiry"]) if token_data.get("token_expiry") else None
        existing.scopes = token_data.get("scopes", "[]")
        existing.updated_at = datetime.utcnow()
    else:
        new_token = OAuthToken(
            channel_id=channel_id,
            access_token=token_data["access_token"],
            refresh_token=refresh_token,
            token_expiry=datetime.fromisoformat(token_data["token_expiry"]) if token_data.get("token_expiry") else None,
            scopes=token_data.get("scopes", "[]"),
        )
        db.add(new_token)
    db.commit()

    # Fix: URL-encode channel name to prevent open redirect
    return RedirectResponse(url="/admin.html?youtube_auth=success&channel=" + quote(ch.name))


@app.get("/api/youtube/status", response_model=List[YouTubeAuthStatus])
def youtube_auth_status(db: Session = Depends(get_db)):
    """حالة ربط YouTube لكل القنوات"""
    channels = db.query(Channel).filter(Channel.is_active == True).all()
    result = []
    for ch in channels:
        token = db.query(OAuthToken).filter(OAuthToken.channel_id == ch.id).first()
        status = YouTubeAuthStatus(
            channel_id=ch.id,
            channel_name=ch.display_name or ch.name,
            has_token=token is not None,
            token_expiry=token.token_expiry if token else None,
        )
        result.append(status)
    return result


@app.post("/api/youtube/check/{channel_id}")
def youtube_check_auth(channel_id: int, db: Session = Depends(get_db)):
    """فحص صلاحية التوكن والتجديد لو لازم"""
    from app.youtube import check_channel_auth

    token = db.query(OAuthToken).filter(OAuthToken.channel_id == channel_id).first()
    if not token:
        raise HTTPException(404, "القناة مش مربوطة بيوتيوب")

    token_data = {
        "access_token": token.access_token,
        "refresh_token": token.refresh_token,
        "token_expiry": token.token_expiry.isoformat() if token.token_expiry else None,
    }
    result = check_channel_auth(token_data)

    # لو التوكن اتجدد، نحدّث في DB
    updated = result.get("token_data", {})
    if updated.get("_refreshed"):
        token.access_token = updated["access_token"]
        if updated.get("token_expiry"):
            token.token_expiry = datetime.fromisoformat(updated["token_expiry"])
        token.updated_at = datetime.utcnow()
        db.commit()

    # Fix: sanitize error message — don't expose internal details
    error_msg = None
    if not result["valid"]:
        raw_error = result.get("error", "")
        if "invalid_grant" in raw_error.lower() or "token" in raw_error.lower():
            error_msg = "التوكن منتهي — اربط القناة تاني"
        elif "no channel" in raw_error.lower():
            error_msg = "مفيش قناة مرتبطة بالحساب ده"
        else:
            error_msg = "فشل التحقق من التوكن"

    return {
        "valid": result["valid"],
        "youtube_channel_title": result.get("channel_title"),
        "error": error_msg,
    }


@app.post("/api/youtube/upload/{topic_id}/{platform_id}", response_model=YouTubeUploadResponse)
async def youtube_upload(
    topic_id: int,
    platform_id: int,
    req: YouTubeUploadRequest,
    db: Session = Depends(get_db),
):
    """رفع فيديو على يوتيوب"""
    from app.youtube import upload_video, set_thumbnail, QUOTA_UPLOAD, QUOTA_THUMBNAIL, QUOTA_DAILY_LIMIT
    from sqlalchemy import text as sql_text

    # تحقق من الموظف
    emp = db.query(Employee).filter(Employee.id == req.employee_id, Employee.is_active == True).first()
    if not emp:
        raise HTTPException(404, "الموظف مش موجود")

    # Fix: validate publish_at requires private privacy
    if req.publish_at and req.privacy != "private":
        raise HTTPException(400, "الجدولة محتاجة privacy=private")

    # تحقق من الموضوع والتوكن والملف — قبل القفل عشان لو فشلوا مش نقفل من غير فايدة
    pd = db.query(PlatformData).filter(
        PlatformData.topic_id == topic_id,
        PlatformData.platform_id == platform_id,
    ).first()
    if not pd:
        raise HTTPException(404, "بيانات المنصة مش موجودة")
    if pd.upload_status == "uploaded":
        raise HTTPException(400, "الفيديو اترفع قبل كده")

    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(404, "الموضوع مش موجود")

    # التوكن — فحص قبل القفل
    token = db.query(OAuthToken).filter(OAuthToken.channel_id == topic.channel_id).first()
    if not token:
        raise HTTPException(400, "القناة مش مربوطة بيوتيوب — اربطها الأول من صفحة الأدمن")

    # فيديو — فحص قبل القفل
    if not topic.video_path or not os.path.exists(topic.video_path):
        raise HTTPException(400, "ملف الفيديو مش موجود")

    # Atomically mark as "uploading" to prevent duplicate uploads
    from sqlalchemy import update
    rows = db.execute(
        update(PlatformData)
        .where(
            PlatformData.topic_id == topic_id,
            PlatformData.platform_id == platform_id,
            PlatformData.upload_status.in_(["pending", "locked"]),
        )
        .values(upload_status="uploading", lock_holder=req.employee_id, lock_time=datetime.utcnow())
    ).rowcount
    db.commit()
    if rows == 0:
        raise HTTPException(409, "الفيديو بيترفع حالياً أو اترفع قبل كده")

    # Refresh pd after atomic UPDATE to sync ORM state
    db.refresh(pd)

    # Fix: atomic quota reservation via SQL UPDATE...WHERE
    from datetime import date
    from sqlalchemy import text as sql_text
    today_str = date.today().isoformat()
    needed = QUOTA_UPLOAD + (QUOTA_THUMBNAIL if topic.thumbnail_path else 0)

    # Try atomic increment (only succeeds if within limit)
    rows = db.execute(
        sql_text(
            "UPDATE quota_usage SET units_used = units_used + :needed "
            "WHERE channel_id = :ch AND date = :dt AND units_used + :needed <= :limit"
        ),
        {"needed": needed, "ch": topic.channel_id, "dt": today_str, "limit": QUOTA_DAILY_LIMIT},
    ).rowcount
    if rows == 0:
        # Either row doesn't exist or quota exceeded
        quota = db.query(QuotaUsage).filter(
            QuotaUsage.channel_id == topic.channel_id,
            QuotaUsage.date == today_str,
        ).first()
        if not quota:
            # First usage today — create row (handle concurrent insert race)
            try:
                db.add(QuotaUsage(channel_id=topic.channel_id, date=today_str, units_used=needed))
                db.commit()
            except SQLIntegrityError:
                db.rollback()
                # Row was created by concurrent request — retry atomic UPDATE
                retry_rows = db.execute(
                    sql_text(
                        "UPDATE quota_usage SET units_used = units_used + :needed "
                        "WHERE channel_id = :ch AND date = :dt AND units_used + :needed <= :limit"
                    ),
                    {"needed": needed, "ch": topic.channel_id, "dt": today_str, "limit": QUOTA_DAILY_LIMIT},
                ).rowcount
                db.commit()
                if retry_rows == 0:
                    pd.upload_status = "pending"
                    pd.lock_holder = None
                    pd.lock_time = None
                    db.commit()
                    raise HTTPException(429, "الكوتا خلصت")
        else:
            # Quota exceeded — rollback upload status
            pd.upload_status = "pending"
            pd.lock_holder = None
            pd.lock_time = None
            db.commit()
            raise HTTPException(429, f"الكوتا خلصت — مستخدم {quota.units_used}/{QUOTA_DAILY_LIMIT} وحدة النهاردة")
    else:
        db.commit()

    # بيانات المنصة — Fix: wrap json.loads in try/except
    try:
        field_values = json.loads(pd.field_values) if pd.field_values else {}
    except (json.JSONDecodeError, TypeError):
        field_values = {}
    title = field_values.get("title", topic.title or f"Video #{topic.topic_number}")
    description = field_values.get("description", "")
    tags_raw = field_values.get("tags", "")
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if isinstance(tags_raw, str) else tags_raw

    # category
    channel = db.query(Channel).filter(Channel.id == topic.channel_id).first()
    category_id = (channel.youtube_category_id if channel else None) or 22

    token_data = {
        "access_token": token.access_token,
        "refresh_token": token.refresh_token,
        "token_expiry": token.token_expiry.isoformat() if token.token_expiry else None,
    }

    try:
        import functools
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, functools.partial(
            upload_video,
            token_data=token_data,
            video_path=topic.video_path,
            title=title,
            description=description,
            tags=tags,
            category_id=category_id,
            privacy=req.privacy,
            publish_at=req.publish_at,
        ))
    except FileNotFoundError:
        # Rollback upload status + quota on failure
        pd.upload_status = "pending"
        pd.lock_holder = None
        pd.lock_time = None
        db.execute(sql_text(
            "UPDATE quota_usage SET units_used = MAX(0, units_used - :needed) WHERE channel_id = :ch AND date = :dt"
        ), {"needed": needed, "ch": topic.channel_id, "dt": today_str})
        db.commit()
        _telegram_upload_failure(db, topic, platform_id, "ملف الفيديو مش موجود", req.employee_id)
        raise HTTPException(400, "ملف الفيديو مش موجود")
    except Exception:
        # Rollback + sanitize error (don't leak internal details)
        pd.upload_status = "pending"
        pd.lock_holder = None
        pd.lock_time = None
        db.execute(sql_text(
            "UPDATE quota_usage SET units_used = MAX(0, units_used - :needed) WHERE channel_id = :ch AND date = :dt"
        ), {"needed": needed, "ch": topic.channel_id, "dt": today_str})
        db.commit()
        _telegram_upload_failure(db, topic, platform_id, "خطأ في الرفع", req.employee_id)
        raise HTTPException(500, "فشل رفع الفيديو على يوتيوب")

    total_quota = result.get("quota_used", QUOTA_UPLOAD)

    # رفع الصورة المصغرة لو موجودة
    if topic.thumbnail_path and os.path.exists(topic.thumbnail_path):
        try:
            thumb_result = set_thumbnail(result["token_data"], result.get("video_id", ""), topic.thumbnail_path)
            total_quota += thumb_result.get("quota_used", 0)
            if thumb_result.get("token_data", {}).get("_refreshed"):
                result["token_data"] = thumb_result["token_data"]
        except Exception:
            pass  # الثامبنيل مش critical

    # تحديث التوكن لو اتجدد
    updated_token = result.get("token_data", {})
    if updated_token.get("_refreshed"):
        token.access_token = updated_token["access_token"]
        if updated_token.get("token_expiry"):
            token.token_expiry = datetime.fromisoformat(updated_token["token_expiry"])
        token.updated_at = datetime.utcnow()

    # Quota already pre-reserved — adjust if actual differs from estimate
    actual_diff = total_quota - needed
    if actual_diff != 0:
        db.execute(sql_text(
            "UPDATE quota_usage SET units_used = MAX(0, units_used + :diff) WHERE channel_id = :ch AND date = :dt"
        ), {"diff": actual_diff, "ch": topic.channel_id, "dt": today_str})

    # تحديث حالة الرفع
    pd.upload_status = "uploaded"
    pd.uploaded_by = req.employee_id
    pd.uploaded_at = datetime.utcnow()
    pd.external_id = result.get("video_id", "")

    # سجل
    db.add(UploadLog(
        topic_id=topic_id,
        platform_id=platform_id,
        employee_id=req.employee_id,
        action="youtube_upload",
        details=json.dumps({"video_id": result.get("video_id", ""), "quota_used": total_quota, "privacy": req.privacy}),
    ))

    # تحديث حالة الموضوع
    all_pd = db.query(PlatformData).filter(PlatformData.topic_id == topic_id).all()
    all_uploaded = all(p.upload_status == "uploaded" for p in all_pd)
    topic.status = "completed" if all_uploaded else "partial"

    # Cross-post: نسخ البيانات للمنصات التانية
    _cross_post(db, topic_id, platform_id)

    # Fix: wrap commit in try/except — video already uploaded to YouTube (irreversible)
    try:
        db.commit()
    except Exception:
        db.rollback()
        # Force save at minimum the upload status to avoid orphaned uploads
        try:
            db2 = None
            from app.database import SessionLocal
            db2 = SessionLocal()
            pd2 = db2.query(PlatformData).filter(
                PlatformData.topic_id == topic_id,
                PlatformData.platform_id == platform_id,
            ).first()
            if pd2:
                pd2.upload_status = "uploaded"
                pd2.uploaded_by = req.employee_id
                pd2.uploaded_at = datetime.utcnow()
                pd2.external_id = result.get("video_id", "")
                db2.commit()
        except Exception:
            pass
        finally:
            if db2:
                db2.close()

    # Telegram notification
    try:
        from app.telegram import notify_upload_success, notify_quota_warning, is_configured
        if is_configured():
            channel = db.query(Channel).filter(Channel.id == topic.channel_id).first()
            emp = db.query(Employee).filter(Employee.id == req.employee_id).first()
            field_vals = json.loads(pd.field_values or "{}")
            notify_upload_success(
                channel_name=channel.display_name or channel.name if channel else "",
                topic_number=topic.topic_number,
                platform_name="يوتيوب",
                title=field_vals.get("title", topic.title or ""),
                video_id=result.get("video_id", ""),
                employee_name=emp.name if emp else "",
            )
            # Quota warning if > 80%
            from app.youtube import QUOTA_DAILY_LIMIT
            from datetime import date
            quota_row = db.query(QuotaUsage).filter(
                QuotaUsage.channel_id == topic.channel_id,
                QuotaUsage.date == date.today().isoformat(),
            ).first()
            if quota_row and quota_row.units_used > QUOTA_DAILY_LIMIT * 0.8:
                notify_quota_warning(
                    channel_name=channel.display_name or channel.name if channel else "",
                    used=quota_row.units_used,
                    limit=QUOTA_DAILY_LIMIT,
                )
    except Exception:
        pass  # Telegram failure is not critical

    return YouTubeUploadResponse(
        video_id=result.get("video_id", ""),
        status="uploaded",
        quota_used=total_quota,
    )


@app.get("/api/youtube/quota/{channel_id}", response_model=QuotaStatusResponse)
def youtube_quota(channel_id: int, db: Session = Depends(get_db)):
    """حالة الكوتا لقناة معينة"""
    from app.youtube import QUOTA_UPLOAD, QUOTA_DAILY_LIMIT

    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "القناة مش موجودة")

    from datetime import date
    today_str = date.today().isoformat()
    quota = db.query(QuotaUsage).filter(
        QuotaUsage.channel_id == channel_id,
        QuotaUsage.date == today_str,
    ).first()

    used = quota.units_used if quota else 0
    remaining = max(0, QUOTA_DAILY_LIMIT - used)

    return QuotaStatusResponse(
        channel_id=channel_id,
        channel_name=ch.display_name or ch.name,
        date=today_str,
        units_used=used,
        units_remaining=remaining,
        daily_limit=QUOTA_DAILY_LIMIT,
        uploads_remaining=remaining // QUOTA_UPLOAD if remaining > 0 else 0,
    )


@app.delete("/api/youtube/disconnect/{channel_id}")
def youtube_disconnect(channel_id: int, db: Session = Depends(get_db)):
    """فصل قناة يوتيوب"""
    token = db.query(OAuthToken).filter(OAuthToken.channel_id == channel_id).first()
    if not token:
        raise HTTPException(404, "القناة مش مربوطة أصلاً")

    # Guard: check for in-progress uploads
    uploading = db.query(PlatformData).join(Topic).filter(
        Topic.channel_id == channel_id,
        PlatformData.upload_status == "uploading",
    ).count()
    if uploading > 0:
        raise HTTPException(409, f"مينفعش — فيه {uploading} فيديو بيترفع حالياً")

    db.delete(token)
    db.commit()
    return {"message": "تم فصل القناة من يوتيوب"}


# ========== Word Batch Import ==========

@app.post("/api/import/word", response_model=WordImportResponse)
async def import_word(
    file: UploadFile = File(...),
    channel_id: int = Form(...),
    content_type: str = Form("shorts"),
    platform_ids: str = Form(""),
    db: Session = Depends(get_db),
):
    """استيراد مواضيع من ملف Word (.docx)"""
    if not file.filename or not file.filename.endswith('.docx'):
        raise HTTPException(400, "الملف لازم يكون .docx")

    if content_type not in ("shorts", "long"):
        raise HTTPException(400, "content_type لازم يكون shorts أو long")

    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "القناة مش موجودة")

    # Read file with size limit (10MB)
    MAX_IMPORT_SIZE = 10 * 1024 * 1024
    content = await file.read(MAX_IMPORT_SIZE + 1)
    if len(content) > MAX_IMPORT_SIZE:
        raise HTTPException(400, "الملف أكبر من 10MB")

    # Save to temp file
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.docx')
    try:
        with os.fdopen(tmp_fd, 'wb') as tmp:
            tmp.write(content)

        # Build platform and field maps from DB
        all_platforms = db.query(Platform).filter(Platform.is_active == True).all()
        platform_map = {}
        field_map = {}

        for p in all_platforms:
            platform_map[p.display_name or p.name] = p.id
            platform_map[p.name] = p.id
            fields = db.query(PlatformField).filter(PlatformField.platform_id == p.id).all()
            field_map[p.id] = {}
            for f in fields:
                field_map[p.id][f.field_label or f.field_name] = f.field_name
                field_map[p.id][f.field_name] = f.field_name

        # Parse Word file
        from app.word_import import parse_word_file
        topics_data, parse_errors = parse_word_file(
            tmp_path, channel_id, content_type, platform_map, field_map
        )

        if not topics_data and parse_errors:
            return WordImportResponse(
                created=0, total=0,
                parse_errors=parse_errors, create_errors=[],
            )

        # Create topics
        created = 0
        create_errors = []

        # Parse platform_ids filter
        selected_platform_ids = None
        if platform_ids and platform_ids.strip():
            try:
                selected_platform_ids = [int(x.strip()) for x in platform_ids.split(",") if x.strip()]
            except ValueError:
                raise HTTPException(400, "platform_ids لازم يكون أرقام مفصولة بفاصلة")

        from app.database import SessionLocal
        for t_data in topics_data:
            topic_db = SessionLocal()
            try:
                topic_create = TopicCreate(**t_data)
                create_topic(topic_create, topic_db, target_platform_ids=selected_platform_ids)
                created += 1
            except HTTPException as e:
                create_errors.append(f"موضوع #{t_data.get('topic_number', '?')}: {e.detail}")
            except Exception:
                create_errors.append(f"موضوع #{t_data.get('topic_number', '?')}: خطأ غير متوقع")
            finally:
                topic_db.close()

        return WordImportResponse(
            created=created,
            total=len(topics_data),
            parse_errors=parse_errors,
            create_errors=create_errors,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@app.get("/api/import/template")
def import_template(db: Session = Depends(get_db)):
    """تحميل قالب Word فارغ بالعناوين الصحيحة"""
    from app.word_import import generate_template
    from fastapi.responses import Response

    all_platforms = db.query(Platform).filter(Platform.is_active == True).all()
    platforms_with_fields = []
    for p in all_platforms:
        fields = db.query(PlatformField).filter(
            PlatformField.platform_id == p.id
        ).order_by(PlatformField.display_order).all()
        platforms_with_fields.append({
            'name': p.name,
            'display_name': p.display_name,
            'fields': [
                {'field_name': f.field_name, 'field_label': f.field_label}
                for f in fields
            ],
        })

    docx_bytes = generate_template(platforms_with_fields)
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=import_template.docx"},
    )


# ========== MG Ranner Import ==========

@app.post("/api/import/mg-ranner-parse")
async def parse_mg_ranner_upload(file: UploadFile = File(...)):
    """تحليل ملف MG Ranner scripts_output.docx واستخراج الحقول — بدون تسجيل في DB"""
    if not file.filename or not file.filename.endswith('.docx'):
        raise HTTPException(400, "الملف لازم يكون .docx")

    MAX_IMPORT_SIZE = 10 * 1024 * 1024
    content = await file.read(MAX_IMPORT_SIZE + 1)
    if len(content) > MAX_IMPORT_SIZE:
        raise HTTPException(400, "الملف أكبر من 10MB")

    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.docx')
    try:
        with os.fdopen(tmp_fd, 'wb') as tmp:
            tmp.write(content)

        from app.mg_ranner_import import parse_mg_ranner_docx
        topics, errors = parse_mg_ranner_docx(tmp_path)
        return {"topics": topics, "errors": errors}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ========== TikTok Playwright ==========

@app.post("/api/tiktok/upload/{topic_id}/{platform_id}", response_model=TikTokUploadResponse)
async def tiktok_upload(
    topic_id: int,
    platform_id: int,
    req: TikTokUploadRequest,
    db: Session = Depends(get_db),
):
    """فتح متصفح Playwright لرفع فيديو على تيكتوك"""
    from app.tiktok import is_playwright_available, is_session_active, start_tiktok_upload

    if not is_playwright_available():
        raise HTTPException(
            400,
            "playwright مش منصّب — شغّل: pip install playwright && playwright install chromium",
        )

    # تحقق من الموظف
    emp = db.query(Employee).filter(Employee.id == req.employee_id, Employee.is_active == True).first()
    if not emp:
        raise HTTPException(404, "الموظف مش موجود")

    # تحقق من بيانات المنصة
    pd = db.query(PlatformData).filter(
        PlatformData.topic_id == topic_id,
        PlatformData.platform_id == platform_id,
    ).first()
    if not pd:
        raise HTTPException(404, "بيانات المنصة مش موجودة")
    if pd.upload_status == "uploaded":
        raise HTTPException(400, "الفيديو اترفع بالفعل")
    if pd.upload_status == "uploading":
        raise HTTPException(400, "الفيديو بيترفع حالياً — استنى يخلص")

    # تحقق إن المنصة تيكتوك
    platform = db.query(Platform).filter(Platform.id == platform_id).first()
    if not platform or platform.name.lower() != "tiktok":
        raise HTTPException(400, "المنصة دي مش تيكتوك")

    # تحقق من ملف الفيديو
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(404, "الموضوع مش موجود")
    if not topic.video_path or not os.path.exists(topic.video_path):
        raise HTTPException(400, "ملف الفيديو مش موجود")

    # تحقق إن مفيش متصفح مفتوح بالفعل
    if is_session_active(topic_id, platform_id):
        return TikTokUploadResponse(
            status="already_running",
            message="المتصفح مفتوح بالفعل للموضوع ده",
        )

    # استخراج بيانات المنصة
    try:
        field_values = json.loads(pd.field_values) if pd.field_values else {}
    except (json.JSONDecodeError, TypeError):
        field_values = {}

    description = field_values.get("description", "")
    hashtags = field_values.get("hashtags", "")

    # سجل العملية
    db.add(UploadLog(
        topic_id=topic_id,
        platform_id=platform_id,
        employee_id=req.employee_id,
        action="tiktok_browser_open",
        details=json.dumps({"video_path": topic.video_path}),
    ))
    db.commit()

    # تشغيل المتصفح في الخلفية
    result = await start_tiktok_upload(
        topic_id=topic_id,
        platform_id=platform_id,
        video_path=topic.video_path,
        description=description,
        hashtags=hashtags,
    )

    return TikTokUploadResponse(status=result["status"], message=result["message"])
