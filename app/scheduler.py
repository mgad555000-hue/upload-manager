"""
حساب التوقيت التلقائي — Upload Manager
يحسب أول slot فاضي من schedule_rules لكل قناة/منصة
All schedule times stored as Cairo local time (Africa/Cairo)
"""
import json
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from app.database import ScheduleRule, PlatformData, Platform

CAIRO_TZ = ZoneInfo("Africa/Cairo")

def _now_cairo() -> datetime:
    """Current time in Cairo, returned as naive datetime"""
    return datetime.now(CAIRO_TZ).replace(tzinfo=None)


def calculate_next_slot(db: Session, channel_id: int, platform_id: int, content_type: str = "shorts", start_from: datetime | None = None) -> datetime | None:
    """
    يحسب أول موعد نشر فاضي لقناة ومنصة معينة.
    1. يجيب قواعد الجدول (publish_times)
    2. يجيب كل المواعيد المحجوزة (pre-fetch)
    3. يرجع أول slot فاضي
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
            continue
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

    # Start searching from: custom start_from > last booked > now (Cairo time)
    now = _now_cairo()
    if start_from:
        search_from = start_from
        if last_booked and last_booked[0] and last_booked[0] >= start_from:
            search_from = last_booked[0] + timedelta(minutes=1)
    elif last_booked and last_booked[0]:
        search_from = max(now, last_booked[0] + timedelta(minutes=1))
    else:
        search_from = now

    # Pre-fetch ALL booked slots for this channel+platform (365 days ahead)
    current_date = search_from.date()
    end_date = current_date + timedelta(days=365)
    booked_rows = db.query(PlatformData.scheduled_time).join(
        PlatformData.topic
    ).filter(
        PlatformData.platform_id == platform_id,
        PlatformData.scheduled_time != None,
        PlatformData.scheduled_time >= datetime.combine(current_date, time(0, 0)),
        PlatformData.scheduled_time <= datetime.combine(end_date, time(23, 59)),
        PlatformData.topic.has(channel_id=channel_id),
    ).all()
    booked_set = {row[0] for row in booked_rows}

    # Search for first free slot
    for day_offset in range(365):
        check_date = current_date + timedelta(days=day_offset)
        for slot_time in time_slots:
            candidate = datetime.combine(check_date, slot_time)
            if candidate <= search_from:
                continue
            if candidate not in booked_set:
                return candidate

    return None


def auto_schedule_topic(db: Session, topic_id: int, channel_id: int, content_type: str = "shorts", start_from: datetime | None = None):
    """
    يحسب ويحط التوقيت لكل منصة لموضوع جديد.
    يُستدعى بعد إنشاء الموضوع.
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


def reschedule_from(db: Session, topic_id: int, platform_id: int, new_time: datetime, cascade: bool = False):
    """
    يغيّر موعد فيديو معين على منصة معينة.
    لو cascade=True: يغيّر كل الفيديوهات اللي بعده على نفس القناة/المنصة
    بناءً على قواعد الجدولة (ScheduleRule).
    يرجع عدد الفيديوهات اللي اتغيرت.
    """
    from app.database import Topic

    # Get the target platform_data
    target_pd = db.query(PlatformData).filter(
        PlatformData.topic_id == topic_id,
        PlatformData.platform_id == platform_id,
    ).first()
    if not target_pd:
        return 0

    # Get the topic to find channel
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        return 0

    # Don't reschedule uploaded videos
    if target_pd.upload_status == "uploaded":
        return 0

    # Update target video
    target_pd.scheduled_time = new_time
    changed = 1

    if cascade:
        # Get schedule rule for this channel+platform
        rule = db.query(ScheduleRule).filter(
            ScheduleRule.channel_id == topic.channel_id,
            ScheduleRule.platform_id == platform_id,
            ScheduleRule.content_type == topic.content_type,
            ScheduleRule.is_active == True,
        ).first()

        if rule:
            try:
                times = json.loads(rule.publish_times)
            except (json.JSONDecodeError, TypeError):
                times = []

            time_slots = []
            for t in times:
                try:
                    if not isinstance(t, str):
                        continue
                    parts = t.split(":")
                    time_slots.append(time(int(parts[0]), int(parts[1])))
                except (IndexError, ValueError, TypeError):
                    continue
            time_slots.sort()

            if time_slots:
                # Get all subsequent videos (same channel + platform, topic_number > current, not uploaded)
                subsequent = db.query(PlatformData).join(
                    PlatformData.topic
                ).filter(
                    PlatformData.platform_id == platform_id,
                    PlatformData.upload_status != "uploaded",
                    Topic.channel_id == topic.channel_id,
                    Topic.content_type == topic.content_type,
                    Topic.topic_number > topic.topic_number,
                ).order_by(Topic.topic_number.asc()).all()

                # Collect IDs of videos being rescheduled (target + subsequent)
                rescheduled_ids = {target_pd.id} | {spd.id for spd in subsequent}

                # Pre-fetch booked slots by OTHER videos (not being rescheduled)
                # to avoid double-booking the same time slot
                end_date = new_time.date() + timedelta(days=90)
                booked_rows = db.query(PlatformData.scheduled_time).join(
                    PlatformData.topic
                ).filter(
                    PlatformData.platform_id == platform_id,
                    PlatformData.scheduled_time != None,
                    PlatformData.id.notin_(rescheduled_ids),
                    Topic.channel_id == topic.channel_id,
                    PlatformData.scheduled_time >= new_time,
                    PlatformData.scheduled_time <= datetime.combine(end_date, time(23, 59)),
                ).all()
                booked_set = {row[0] for row in booked_rows}

                # Assign next available slots sequentially after new_time, skipping booked
                last_assigned = new_time
                for spd in subsequent:
                    search_date = last_assigned.date()
                    found = False
                    for day_offset in range(90):
                        check_date = search_date + timedelta(days=day_offset)
                        for slot_time in time_slots:
                            candidate = datetime.combine(check_date, slot_time)
                            if candidate > last_assigned and candidate not in booked_set:
                                spd.scheduled_time = candidate
                                last_assigned = candidate
                                changed += 1
                                found = True
                                break
                        if found:
                            break

    db.commit()
    return changed
