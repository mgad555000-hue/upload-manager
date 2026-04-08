"""
Telegram Bot Notifications — Upload Manager
إشعارات تليجرام: نجاح/فشل الرفع + تقرير الكوتا اليومي
"""
import os
import json
import urllib.request
import urllib.parse
from datetime import datetime

# Environment variables
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def is_configured() -> bool:
    return bool(BOT_TOKEN and CHAT_ID)


def send_message(text: str) -> bool:
    """إرسال رسالة عبر Telegram Bot API"""
    if not is_configured():
        return False
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[Telegram] Send failed: {e}")
        return False


def notify_upload_success(
    channel_name: str,
    topic_number: int,
    platform_name: str,
    title: str = "",
    video_id: str = "",
    employee_name: str = "",
):
    """إشعار نجاح الرفع"""
    lines = [
        "✅ <b>تم الرفع بنجاح</b>",
        f"📺 القناة: <b>{_esc(channel_name)}</b>",
        f"📝 موضوع #{topic_number}",
        f"📱 المنصة: {_esc(platform_name)}",
    ]
    if title:
        lines.append(f"🏷 العنوان: {_esc(title)}")
    if video_id:
        lines.append(f"🔗 https://youtu.be/{video_id}")
    if employee_name:
        lines.append(f"👤 بواسطة: {_esc(employee_name)}")
    send_message("\n".join(lines))


def notify_upload_failure(
    channel_name: str,
    topic_number: int,
    platform_name: str,
    error: str = "",
    employee_name: str = "",
):
    """إشعار فشل الرفع"""
    lines = [
        "❌ <b>فشل الرفع</b>",
        f"📺 القناة: <b>{_esc(channel_name)}</b>",
        f"📝 موضوع #{topic_number}",
        f"📱 المنصة: {_esc(platform_name)}",
    ]
    if error:
        lines.append(f"⚠️ السبب: {_esc(error)}")
    if employee_name:
        lines.append(f"👤 بواسطة: {_esc(employee_name)}")
    send_message("\n".join(lines))


def notify_quota_warning(channel_name: str, used: int, limit: int):
    """تحذير الكوتا"""
    pct = int(used / limit * 100) if limit > 0 else 0
    send_message(
        f"⚠️ <b>تحذير كوتا</b>\n"
        f"📺 القناة: <b>{_esc(channel_name)}</b>\n"
        f"📊 الاستخدام: {used}/{limit} ({pct}%)\n"
        f"⏰ {datetime.utcnow().strftime('%Y-%m-%d')}"
    )


def notify_daily_summary(stats: dict):
    """تقرير يومي"""
    lines = [
        f"📊 <b>تقرير يومي — {datetime.utcnow().strftime('%Y-%m-%d')}</b>",
        f"✅ تم رفع: <b>{stats.get('uploaded_today', 0)}</b> فيديو",
        f"⏳ في الانتظار: {stats.get('pending', 0)}",
        f"🔒 مقفول: {stats.get('locked', 0)}",
    ]
    if stats.get("quota_info"):
        for q in stats["quota_info"]:
            lines.append(f"📺 {_esc(q['channel'])}: {q['used']}/{q['limit']} وحدة")
    send_message("\n".join(lines))


def _esc(s: str) -> str:
    """Escape HTML for Telegram"""
    if not s:
        return ""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
