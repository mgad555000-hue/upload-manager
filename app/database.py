"""
قاعدة بيانات Upload Manager — SQLite
8 جداول: channels, platforms, platform_fields, topics, platform_data, employees, upload_log, schedule_rules
"""
from sqlalchemy import (
    create_engine, Column, String, Integer, DateTime, Text, Boolean,
    ForeignKey, UniqueConstraint, inspect, text
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
import os
import sys
import json

# مسار قاعدة البيانات
if sys.platform == "win32":
    _db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "upload_manager.db")
    os.makedirs(os.path.dirname(_db_path), exist_ok=True)
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_db_path}")
else:
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////app/data/upload_manager.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ========== الجداول ==========

class Channel(Base):
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    display_name = Column(String, nullable=True)
    youtube_channel_id = Column(String, nullable=True)
    facebook_page_id = Column(String, nullable=True)
    default_hashtags = Column(Text, nullable=True)  # JSON array
    default_links = Column(Text, nullable=True)
    youtube_category_id = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    topics = relationship("Topic", back_populates="channel")
    schedule_rules = relationship("ScheduleRule", back_populates="channel")


class Platform(Base):
    __tablename__ = "platforms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    display_name = Column(String, nullable=True)
    mode = Column(String, nullable=False, default="manual")  # auto / manual
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    fields = relationship("PlatformField", back_populates="platform")
    schedule_rules = relationship("ScheduleRule", back_populates="platform")


class PlatformField(Base):
    __tablename__ = "platform_fields"

    id = Column(Integer, primary_key=True, index=True)
    platform_id = Column(Integer, ForeignKey("platforms.id"), nullable=False)
    field_name = Column(String, nullable=False)
    field_label = Column(String, nullable=True)
    field_type = Column(String, default="text")  # text, textarea, tags
    is_required = Column(Boolean, default=True)
    is_copyable = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    platform = relationship("Platform", back_populates="fields")


class Topic(Base):
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    topic_number = Column(Integer, nullable=False)
    content_type = Column(String, default="shorts")  # shorts / long
    title = Column(String, nullable=True)
    thumbnail_path = Column(String, nullable=True)
    video_path = Column(String, nullable=True)
    batch_number = Column(Integer, nullable=True)
    priority = Column(Integer, default=0)
    status = Column(String, default="pending")  # pending / partial / completed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("channel_id", "topic_number", "content_type", name="uq_topic"),
    )

    channel = relationship("Channel", back_populates="topics")
    platform_data = relationship("PlatformData", back_populates="topic", cascade="all, delete-orphan")
    logs = relationship("UploadLog", back_populates="topic", cascade="all, delete-orphan")


class PlatformData(Base):
    __tablename__ = "platform_data"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=False)
    platform_id = Column(Integer, ForeignKey("platforms.id"), nullable=False)
    field_values = Column(Text, nullable=False, default="{}")  # JSON
    scheduled_time = Column(DateTime, nullable=True)
    upload_status = Column(String, default="pending")  # pending / locked / uploaded
    lock_holder = Column(Integer, ForeignKey("employees.id"), nullable=True)
    lock_time = Column(DateTime, nullable=True)
    uploaded_by = Column(Integer, ForeignKey("employees.id"), nullable=True)
    uploaded_at = Column(DateTime, nullable=True)
    bot_processed = Column(Boolean, default=False)
    bot_processed_at = Column(DateTime, nullable=True)
    external_id = Column(String, nullable=True)  # YouTube video ID
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("topic_id", "platform_id", name="uq_topic_platform"),
    )

    topic = relationship("Topic", back_populates="platform_data")
    platform = relationship("Platform")


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    pin = Column(String, nullable=False, unique=True)
    role = Column(String, default="uploader")  # uploader / admin
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class UploadLog(Base):
    __tablename__ = "upload_log"

    id = Column(Integer, primary_key=True, index=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=True)
    platform_id = Column(Integer, ForeignKey("platforms.id"), nullable=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    action = Column(String, nullable=False)
    details = Column(Text, nullable=True)  # JSON
    created_at = Column(DateTime, default=datetime.utcnow)

    topic = relationship("Topic", back_populates="logs")
    platform = relationship("Platform")
    employee = relationship("Employee")


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False, unique=True)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=False)
    token_expiry = Column(DateTime, nullable=True)
    scopes = Column(Text, nullable=True)  # JSON array
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    channel = relationship("Channel")


class QuotaUsage(Base):
    __tablename__ = "quota_usage"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    date = Column(String, nullable=False)  # YYYY-MM-DD
    units_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("channel_id", "date", name="uq_quota_channel_date"),
    )

    channel = relationship("Channel")


class ScheduleRule(Base):
    __tablename__ = "schedule_rules"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    platform_id = Column(Integer, ForeignKey("platforms.id"), nullable=False)
    publish_times = Column(Text, nullable=False)  # JSON: ["08:00","10:00",...]
    content_type = Column(String, default="shorts")
    timezone = Column(String, default="Africa/Cairo")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("channel_id", "platform_id", "content_type", name="uq_schedule_rule"),
    )

    channel = relationship("Channel", back_populates="schedule_rules")
    platform = relationship("Platform", back_populates="schedule_rules")


# ========== Seed Data ==========

def _seed_data():
    """بيانات أولية: 4 منصات + 4 قنوات + حقول + admin"""
    db = SessionLocal()
    try:
        # تحقق لو البيانات موجودة
        if db.query(Platform).count() > 0:
            return

        # المنصات
        platforms = [
            Platform(name="youtube", display_name="يوتيوب", mode="auto"),
            Platform(name="facebook", display_name="فيسبوك", mode="auto"),
            Platform(name="tiktok", display_name="تيكتوك", mode="manual"),
            Platform(name="upscrolled", display_name="أبسكرولد", mode="manual"),
        ]
        db.add_all(platforms)
        db.flush()

        # القنوات
        channels = [
            Channel(name="My_Kidney", display_name="كليتي"),
            Channel(name="Alhashab2000", display_name="الحشب"),
            Channel(name="Social_relations", display_name="علاقات اجتماعية"),
            Channel(name="المساحة_التالتة", display_name="المساحة التالتة"),
        ]
        db.add_all(channels)
        db.flush()

        # حقول المنصات
        yt = platforms[0]  # youtube
        fb = platforms[1]  # facebook
        tk = platforms[2]  # tiktok
        up = platforms[3]  # upscrolled

        fields = [
            # YouTube
            PlatformField(platform_id=yt.id, field_name="title", field_label="العنوان", field_type="text", is_required=True, display_order=1),
            PlatformField(platform_id=yt.id, field_name="description", field_label="الوصف", field_type="textarea", is_required=True, display_order=2),
            PlatformField(platform_id=yt.id, field_name="tags", field_label="الكلمات المفتاحية", field_type="tags", is_required=False, display_order=3),
            PlatformField(platform_id=yt.id, field_name="thumbnail_text", field_label="جملة الصورة المصغرة", field_type="text", is_required=False, display_order=4),
            # Facebook
            PlatformField(platform_id=fb.id, field_name="title", field_label="العنوان", field_type="text", is_required=True, display_order=1),
            PlatformField(platform_id=fb.id, field_name="description", field_label="الوصف", field_type="textarea", is_required=True, display_order=2),
            # TikTok
            PlatformField(platform_id=tk.id, field_name="description", field_label="الوصف", field_type="textarea", is_required=True, display_order=1),
            PlatformField(platform_id=tk.id, field_name="hashtags", field_label="الهاشتاجات", field_type="tags", is_required=False, display_order=2),
            PlatformField(platform_id=tk.id, field_name="screen_text", field_label="جملة الشاشة", field_type="text", is_required=False, display_order=3),
            # Upscrolled
            PlatformField(platform_id=up.id, field_name="description", field_label="الوصف", field_type="textarea", is_required=True, display_order=1),
            PlatformField(platform_id=up.id, field_name="hashtags", field_label="الهاشتاجات", field_type="tags", is_required=False, display_order=2),
            PlatformField(platform_id=up.id, field_name="screen_text", field_label="جملة الشاشة", field_type="text", is_required=False, display_order=3),
        ]
        db.add_all(fields)

        # Admin employee
        admin = Employee(name="Admin", pin="0000", role="admin")
        db.add(admin)

        # قواعد الجدول الافتراضية (8 مواعيد يومية لكل قناة/منصة)
        default_times = json.dumps(["08:00", "10:00", "12:00", "14:00", "16:00", "18:00", "20:00", "22:00"])
        for ch in channels:
            for pl in platforms:
                db.add(ScheduleRule(
                    channel_id=ch.id,
                    platform_id=pl.id,
                    publish_times=default_times,
                    content_type="shorts",
                ))

        db.commit()
        print("[DB] Seed data inserted successfully")
    except Exception as e:
        db.rollback()
        print(f"[DB] Seed error: {e}")
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    _seed_data()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
