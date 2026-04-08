"""
حساب التوقيت التلقائي — Upload Manager
يحسب أول slot فاضي من schedule_rules لكل قناة/منصة
"""
import json
from datetime import datetime, timedelta, time
from sqlalchemy.orm import Session
from app.database import ScheduleRule, PlatformData, Platform


def calculate_next_slot(db: Session, channel_id: int, platform_id: int, content_type: str = "shorts", start_from: datetime | None = None) -> datetime | None:
    """
    يحسب أول موعد نشر فاضي لقناة ومنصة معينة.
    1. يجيب قواعد الجدول (publish_times)
    2. يجيب آخر موعد محجوز
    3. يرجع أول slot فاضي بعده

    start_from: تاريخ بداية مخصص — لو None يبدأ من الوقت الحالي أو بعد آخر محجوز
    """
    rule = db.query(ScheduleRule).filter(
        ScheduleRule.channel_id == channel_id,
        ScheduleRule.platform_id == platform_id,
        ScheduleRule.content_type == content_type,
        ScheduleRule.is_active == True,
    ).first()

    if not rule:
        return None

    try:
        times = json.loads(rule.publish_times)
    except (json.JSONDecodeError, TypeError):
        return None

    if not times:
        return None

    # Parse times to time objects
    time_slots = []
    for t in times:
        try:
            if not isinstance(t, str):
                continue
            parts = t.split(":")
            time_slots.append(time(int(parts[0]), int(parts[1])))
        except (IndexError, ValueError, TypeError):
            continue  # Skip malformed time entries
    if not time_slots:
        return None
    time_slots.sort()

    # Find last booked slot for this channel+platform
    last_booked = db.query(PlatformData.scheduled_time).join(
        PlatformData.topic
    ).filter(
        PlatformData.platform_id == platform_id,
        PlatformData.scheduled_time != None,
        PlatformData.topic.has(channel_id=channel_id),
    ).order_by(PlatformData.scheduled_time.desc()).first()

    # Start searching from: custom start_from > last booked > now
    now = datetime.utcnow()
    if start_from:
        search_from = start_from
        # لو فيه محجوز بعد start_from، ابدأ بعده
        if last_booked and last_booked[0] and last_booked[0] >= start_from:
            search_from = last_booked[0] + timedelta(minutes=1)
    elif last_booked and last_booked[0]:
        search_from = max(now, last_booked[0] + timedelta(minutes=1))
    else:
        search_from = now

    # Search up to 30 days ahead
    current_date = search_from.date()
    for day_offset in range(30):
        check_date = current_date + timedelta(days=day_offset)
        for slot_time in time_slots:
            candidate = datetime.combine(check_date, slot_time)
            if candidate <= search_from:
                continue
            # Check if this slot is already taken
            existing = db.query(PlatformData).join(
                PlatformData.topic
            ).filter(
                PlatformData.platform_id == platform_id,
                PlatformData.scheduled_time == candidate,
                PlatformData.topic.has(channel_id=channel_id),
            ).first()
            if not existing:
                return candidate

    return None


def auto_schedule_topic(db: Session, topic_id: int, channel_id: int, content_type: str = "shorts", start_from: datetime | None = None):
    """
    يحسب ويحط التوقيت لكل منصة لموضوع جديد.
    يُستدعى بعد إنشاء الموضوع.

    start_from: تاريخ بداية مخصص للجدولة — لو None يبدأ من الوقت الحالي
    """
    platform_data_list = db.query(PlatformData).filter(
        PlatformData.topic_id == topic_id,
        PlatformData.scheduled_time == None,
    ).all()

    for pd in platform_data_list:
        next_slot = calculate_next_slot(db, channel_id, pd.platform_id, content_type, start_from=start_from)
        if next_slot:
            pd.scheduled_time = next_slot

    db.commit()
