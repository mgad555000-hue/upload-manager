"""
نماذج Pydantic للـ API — Upload Manager
"""
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal


# ========== Channels ==========

class ChannelCreate(BaseModel):
    name: str
    display_name: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("اسم القناة مطلوب")
        return v.strip()
    youtube_channel_id: Optional[str] = None
    facebook_page_id: Optional[str] = None
    default_hashtags: Optional[str] = None
    default_links: Optional[str] = None
    youtube_category_id: Optional[int] = None

class ChannelUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError("اسم القناة مطلوب")
        return v.strip() if v else v
    youtube_channel_id: Optional[str] = None
    facebook_page_id: Optional[str] = None
    default_hashtags: Optional[str] = None
    default_links: Optional[str] = None
    youtube_category_id: Optional[int] = None
    is_active: Optional[bool] = None

class ChannelResponse(BaseModel):
    id: int
    name: str
    display_name: Optional[str]
    youtube_channel_id: Optional[str]
    facebook_page_id: Optional[str]
    default_hashtags: Optional[str]
    default_links: Optional[str]
    youtube_category_id: Optional[int]
    is_active: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    class Config:
        from_attributes = True


# ========== Platforms ==========

class PlatformResponse(BaseModel):
    id: int
    name: str
    display_name: Optional[str]
    mode: str
    is_active: bool
    class Config:
        from_attributes = True

class PlatformFieldCreate(BaseModel):
    field_name: str
    field_label: Optional[str] = None
    field_type: Literal["text", "textarea", "tags"] = "text"
    is_required: bool = True
    is_copyable: bool = True
    display_order: int = 0

class PlatformFieldUpdate(BaseModel):
    field_name: Optional[str] = None
    field_label: Optional[str] = None
    field_type: Optional[Literal["text", "textarea", "tags"]] = None
    is_required: Optional[bool] = None
    is_copyable: Optional[bool] = None
    display_order: Optional[int] = None

class PlatformFieldResponse(BaseModel):
    id: int
    platform_id: int
    field_name: str
    field_label: Optional[str]
    field_type: str
    is_required: bool
    is_copyable: bool
    display_order: int
    class Config:
        from_attributes = True


# ========== Topics ==========

class PlatformDataInput(BaseModel):
    platform_id: int
    field_values: Dict[str, Any]
    scheduled_time: Optional[datetime] = None

class TopicCreate(BaseModel):
    channel_id: int
    topic_number: int = Field(ge=1)
    content_type: Literal["shorts", "long"] = "shorts"
    title: Optional[str] = None
    thumbnail_path: Optional[str] = None
    video_path: Optional[str] = None
    batch_number: Optional[int] = None
    priority: Optional[int] = 0
    platform_data: Optional[List[PlatformDataInput]] = None

class TopicUpdate(BaseModel):
    title: Optional[str] = None
    thumbnail_path: Optional[str] = None
    video_path: Optional[str] = None
    batch_number: Optional[int] = None
    priority: Optional[int] = None
    status: Optional[Literal["pending", "partial", "completed"]] = None

class PlatformDataResponse(BaseModel):
    id: int
    topic_id: int
    platform_id: int
    field_values: str  # JSON string
    scheduled_time: Optional[datetime]
    upload_status: str
    lock_holder: Optional[int]
    lock_time: Optional[datetime]
    uploaded_by: Optional[int]
    uploaded_at: Optional[datetime]
    bot_processed: bool
    external_id: Optional[str]
    class Config:
        from_attributes = True

class TopicResponse(BaseModel):
    id: int
    channel_id: int
    topic_number: int
    content_type: str
    title: Optional[str]
    thumbnail_path: Optional[str]
    video_path: Optional[str]
    batch_number: Optional[int]
    priority: int
    status: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    platform_data: Optional[List[PlatformDataResponse]] = None
    class Config:
        from_attributes = True

class TopicBatchCreate(BaseModel):
    topics: List[TopicCreate]
    schedule_start_from: Optional[str] = None  # ISO date: "2026-04-15" or "2026-04-15T08:00:00"


# ========== Employees ==========

class EmployeeCreate(BaseModel):
    name: str
    pin: str
    role: Literal["uploader", "admin"] = "uploader"

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("اسم الموظف مطلوب")
        return v.strip()

    @field_validator("pin")
    @classmethod
    def pin_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("الكود مطلوب")
        return v.strip()

class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    pin: Optional[str] = None
    role: Optional[Literal["uploader", "admin"]] = None
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError("اسم الموظف مطلوب")
        return v.strip() if v else v

    @field_validator("pin")
    @classmethod
    def pin_not_empty(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError("الكود مطلوب")
        return v.strip() if v else v

class EmployeeResponse(BaseModel):
    id: int
    name: str
    role: str
    is_active: bool
    created_at: Optional[datetime]
    class Config:
        from_attributes = True

class LoginRequest(BaseModel):
    pin: str

class LoginResponse(BaseModel):
    employee_id: int
    name: str
    role: str
    token: str


# ========== Upload ==========

class UploadConfirm(BaseModel):
    employee_id: int

class CopyLogRequest(BaseModel):
    employee_id: int
    field_name: str


# ========== Schedule ==========

class ScheduleRuleCreate(BaseModel):
    channel_id: int
    platform_id: int
    publish_times: str  # JSON: ["08:00","10:00",...]
    content_type: Literal["shorts", "long"] = "shorts"
    timezone: str = "Africa/Cairo"

    @field_validator("publish_times")
    @classmethod
    def validate_publish_times(cls, v):
        import json
        try:
            data = json.loads(v)
        except (json.JSONDecodeError, TypeError):
            raise ValueError("publish_times لازم يكون JSON صحيح")
        if not isinstance(data, list):
            raise ValueError("publish_times لازم يكون قائمة مواعيد")
        return v

class ScheduleRuleUpdate(BaseModel):
    publish_times: Optional[str] = None
    content_type: Optional[Literal["shorts", "long"]] = None
    is_active: Optional[bool] = None

    @field_validator("publish_times")
    @classmethod
    def validate_publish_times(cls, v):
        if v is None:
            return v
        import json
        try:
            data = json.loads(v)
        except (json.JSONDecodeError, TypeError):
            raise ValueError("publish_times لازم يكون JSON صحيح")
        if not isinstance(data, list):
            raise ValueError("publish_times لازم يكون قائمة مواعيد")
        return v

class ScheduleRuleResponse(BaseModel):
    id: int
    channel_id: int
    platform_id: int
    publish_times: str
    content_type: str
    timezone: str
    is_active: bool
    class Config:
        from_attributes = True

class RescheduleRequest(BaseModel):
    topic_id: int
    platform_id: int
    new_time: datetime
    cascade: bool = False


# ========== Upload Log ==========

class UploadLogResponse(BaseModel):
    id: int
    topic_id: Optional[int]
    platform_id: Optional[int]
    employee_id: Optional[int]
    action: str
    details: Optional[str]
    created_at: Optional[datetime]
    class Config:
        from_attributes = True


# ========== YouTube ==========

class YouTubeAuthStatus(BaseModel):
    channel_id: int
    channel_name: str
    has_token: bool
    is_valid: Optional[bool] = None
    youtube_channel_title: Optional[str] = None
    token_expiry: Optional[datetime] = None

class YouTubeUploadRequest(BaseModel):
    employee_id: int
    privacy: Literal["private", "public", "unlisted"] = "private"
    publish_at: Optional[datetime] = None

class YouTubeUploadResponse(BaseModel):
    video_id: str
    status: str
    quota_used: int

class QuotaStatusResponse(BaseModel):
    channel_id: int
    channel_name: str
    date: str
    units_used: int
    units_remaining: int
    daily_limit: int
    uploads_remaining: int


# ========== Dashboard ==========

class DashboardStats(BaseModel):
    total_topics: int
    pending_uploads: int
    uploaded_today: int
    locked_now: int


# ========== Word Import ==========

class WordImportResponse(BaseModel):
    created: int
    total: int
    parse_errors: List[str]
    create_errors: List[str]


# ========== TikTok ==========

class TikTokUploadRequest(BaseModel):
    employee_id: int

class TikTokUploadResponse(BaseModel):
    status: str
    message: str
