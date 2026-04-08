"""Seed test data for Upload Manager"""
import json
import urllib.request

API = "http://localhost:8003"

def post(path, data):
    body = json.dumps(data, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(API + path, body, {'Content-Type': 'application/json; charset=utf-8'})
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read())

# Topic 1
t1 = post("/api/topics", {
    "channel_id": 1,
    "topic_number": 47,
    "content_type": "shorts",
    "title": "فيديو عن غسيل الكلى",
    "priority": 1,
    "platform_data": [
        {
            "platform_id": 1,
            "field_values": {
                "title": "غسيل الكلى - متى تحتاجه؟",
                "description": "في الفيديو ده هنتكلم عن غسيل الكلى وامتى بتحتاجه وايه الأعراض اللي لازم تاخد بالك منها",
                "tags": ["kidney", "dialysis", "غسيل الكلى"],
                "thumbnail_text": "غسيل الكلى"
            },
            "scheduled_time": "2026-03-06T08:00:00"
        },
        {
            "platform_id": 3,
            "field_values": {
                "description": "غسيل الكلى مش مخيف زي ما انت فاكر! شوف الفيديو واعرف امتى بتحتاجه",
                "hashtags": ["#غسيل_الكلى", "#كليتي", "#صحة"],
                "screen_text": "غسيل الكلى - الحقيقة كاملة"
            },
            "scheduled_time": "2026-03-06T10:00:00"
        },
        {
            "platform_id": 2,
            "field_values": {
                "title": "غسيل الكلى - كل اللي محتاج تعرفه",
                "description": "فيديو شامل عن غسيل الكلى ومتى تحتاجه"
            },
            "scheduled_time": "2026-03-06T12:00:00"
        },
        {
            "platform_id": 4,
            "field_values": {
                "description": "غسيل الكلى - شوف الفيديو واعرف كل حاجة",
                "hashtags": ["#غسيل_الكلى", "#صحة"],
                "screen_text": "غسيل الكلى"
            },
            "scheduled_time": "2026-03-06T14:00:00"
        }
    ]
})
print(f"Topic 1: #{t1['topic_number']} - {t1['title']} (platforms: {len(t1['platform_data'])})")

# Topic 2
t2 = post("/api/topics", {
    "channel_id": 1,
    "topic_number": 48,
    "content_type": "shorts",
    "title": "الفشل الكلوي الحاد",
    "priority": 2,
    "platform_data": [
        {
            "platform_id": 1,
            "field_values": {
                "title": "الفشل الكلوي الحاد - 5 أعراض خطيرة",
                "description": "اعرف ايه هو الفشل الكلوي الحاد وايه الأعراض الخطيرة اللي لازم تروح الطوارئ فورا",
                "tags": ["kidney failure", "الفشل الكلوي"]
            },
            "scheduled_time": "2026-03-06T16:00:00"
        },
        {
            "platform_id": 3,
            "field_values": {
                "description": "الفشل الكلوي الحاد ممكن يحصل لأي حد! اعرف الأعراض",
                "hashtags": ["#الفشل_الكلوي", "#كليتي"],
                "screen_text": "5 أعراض خطيرة"
            },
            "scheduled_time": "2026-03-06T18:00:00"
        }
    ]
})
print(f"Topic 2: #{t2['topic_number']} - {t2['title']} (platforms: {len(t2['platform_data'])})")

# Topic 3 - different channel
t3 = post("/api/topics", {
    "channel_id": 3,
    "topic_number": 12,
    "content_type": "shorts",
    "title": "كيف تتعامل مع شخص عنيد",
    "priority": 1,
    "platform_data": [
        {
            "platform_id": 1,
            "field_values": {
                "title": "كيف تتعامل مع شخص عنيد؟ 3 نصائح ذهبية",
                "description": "تعلم فن التعامل مع الشخصيات العنيدة بطريقة ذكية"
            },
            "scheduled_time": "2026-03-06T08:00:00"
        },
        {
            "platform_id": 3,
            "field_values": {
                "description": "الشخص العنيد مش مشكلة! تعلم تتعامل معاه",
                "hashtags": ["#علاقات", "#تنمية_بشرية"],
                "screen_text": "3 نصائح ذهبية"
            },
            "scheduled_time": "2026-03-06T10:00:00"
        }
    ]
})
print(f"Topic 3: #{t3['topic_number']} - {t3['title']} (platforms: {len(t3['platform_data'])})")

print("\nAll test data created! Open http://localhost:8003 in browser")
