"""
MG Ranner Import — Parser for scripts_output.docx files
يقرأ ملفات الـ docx من MG Ranner ويستخرج كل الحقول لكل موضوع
يدعم تنسيقين: Markdown (القديم) والنص العادي (الجديد)
"""
import re
from typing import List, Dict, Tuple
from docx import Document


def parse_mg_ranner_docx(file_path: str) -> Tuple[List[Dict], List[str]]:
    """
    Parse a MG Ranner scripts_output.docx file.

    Returns:
        (topics_list, errors_list)
        topics_list = [{"topic_number": int, "fields": {"yt_title_1": str, ...}}]
    """
    topics = []
    errors = []

    try:
        doc = Document(file_path)
    except Exception as e:
        return [], [f"فشل فتح الملف: {str(e)}"]

    # Collect topics: each Heading 2 with "Script N" starts a new topic
    # The content follows in the next Normal paragraph(s)
    current_topic_number = None
    current_content = []

    for para in doc.paragraphs:
        style_name = para.style.name if para.style else ""
        text = para.text.strip()

        if style_name == "Heading 2" and text.startswith("Script"):
            # Save previous topic if exists
            if current_topic_number is not None:
                full_text = "\n".join(current_content)
                result = _parse_topic_content(current_topic_number, full_text)
                if result:
                    topics.append(result)
                else:
                    errors.append(f"Script {current_topic_number}: فشل استخراج الحقول")

            # Extract topic number
            match = re.search(r"Script\s+(\d+)", text)
            if match:
                current_topic_number = int(match.group(1))
                current_content = []
            else:
                errors.append(f"عنوان غير صالح: {text}")
                current_topic_number = None
                current_content = []
        elif current_topic_number is not None:
            if text:
                current_content.append(text)

    # Don't forget the last topic
    if current_topic_number is not None and current_content:
        full_text = "\n".join(current_content)
        result = _parse_topic_content(current_topic_number, full_text)
        if result:
            topics.append(result)
        else:
            errors.append(f"Script {current_topic_number}: فشل استخراج الحقول")

    if not topics:
        errors.append("لم يتم العثور على أي مواضيع في الملف")

    return topics, errors


def _parse_topic_content(topic_number: int, text: str) -> Dict:
    """Parse the full text content of a single topic into structured fields."""
    fields = {}

    # Detect format: markdown (### **القسم) or plain text (القسم الأول:)
    is_markdown = "### **القسم" in text or "**عنوان" in text

    if is_markdown:
        fields = _parse_markdown_format(text)
    else:
        fields = _parse_plain_format(text)

    # Clean up empty fields
    fields = {k: v for k, v in fields.items() if v}

    if not fields:
        return None

    return {
        "topic_number": topic_number,
        "fields": fields,
    }


def _parse_plain_format(text: str) -> Dict:
    """Parse plain text format (no markdown):
    القسم الأول: اليوتيوب
    العنوان: ...
    الوصف: ...
    جملة الشاشة: ...
    الكلمات المفتاحية: ...
    القسم الثاني: التيكتوك
    ...
    """
    fields = {}

    # Split into sections by القسم
    sections = re.split(r'القسم\s+(?:الأول|الثاني|الثالث|الرابع|الخامس)\s*:\s*', text)

    yt_section = ""
    tt_section = ""
    fb_section = ""
    up_section = ""  # جاكو / Upscrolled

    for sec in sections:
        s = sec[:80].lower()
        if "اليوتيوب" in s or "يوتيوب" in s:
            yt_section = sec
        elif "التيكتوك" in s or "تيكتوك" in s or "التيك توك" in s or "تيك توك" in s:
            tt_section = sec
        elif "الفيس بوك" in s or "فيسبوك" in s or "فيس بوك" in s:
            fb_section = sec
        elif "جاكو" in s or "ترجمة" in s or "upscrolled" in s:
            up_section = sec

    # === YouTube Section ===
    if yt_section:
        fields["yt_title_1"] = _extract_plain_field(yt_section, r'العنوان\s*:')
        fields["yt_desc_1"] = _extract_plain_field(yt_section, r'الوصف\s*:')
        fields["yt_screen"] = _extract_plain_screen(yt_section)
        fields["yt_keywords"] = _extract_plain_field(yt_section, r'الكلمات المفتاحية\s*:')

    # === TikTok Section ===
    if tt_section:
        fields["tt_desc"] = _extract_plain_field(tt_section, r'الوصف\s*:')
        fields["tt_screen"] = _extract_plain_screen(tt_section)

    # === Facebook Section ===
    if fb_section:
        fields["fb_desc"] = _extract_plain_field(fb_section, r'الوصف\s*:')
        fields["fb_screen"] = _extract_plain_screen(fb_section)

    # === Upscrolled/Jaco Section ===
    if up_section:
        fields["up_desc"] = _extract_plain_field(up_section, r'الوصف\s*:')
        fields["up_screen"] = _extract_plain_screen(up_section)

    return fields


def _extract_plain_field(section: str, label_pattern: str) -> str:
    """Extract a field value from plain text section.
    Matches label: value — stops at next label or section end."""
    # Known labels that signal end of current field
    next_labels = r'(?:العنوان|الوصف|جملة الشاشة|الكلمات المفتاحية|القسم)\s*:'
    pattern = label_pattern + r'\s*(.*?)(?=' + next_labels + r'|\Z)'
    match = re.search(pattern, section, re.DOTALL)
    if match:
        value = match.group(1).strip()
        # Remove trailing newlines
        value = value.rstrip('\n').strip()
        return value
    return ""


def _extract_plain_screen(section: str) -> str:
    """Extract screen text (جملة الشاشة) — may be multi-line."""
    pattern = r'جملة الشاشة\s*:\s*(.*?)(?=الكلمات المفتاحية\s*:|القسم\s|$)'
    match = re.search(pattern, section, re.DOTALL)
    if match:
        value = match.group(1).strip()
        return value
    return ""


def _parse_markdown_format(text: str) -> Dict:
    """Parse old markdown format with ### and ** markers."""
    fields = {}

    # Split into sections
    sections = re.split(r'###\s*\*\*القسم\s', text)

    yt_section = ""
    tt_section = ""
    fb_section = ""
    tr_section = ""

    for sec in sections:
        s = sec[:60]
        if s.startswith("الأول") or ("اليوتيوب" in s and "ترجمة" not in s):
            yt_section = sec
        elif s.startswith("الثاني") or "التيك توك" in s:
            tt_section = sec
        elif s.startswith("الثالث") or "الفيس بوك" in s:
            fb_section = sec
        elif s.startswith("الرابع") or "ترجمة" in s:
            tr_section = sec

    # === YouTube Section ===
    if yt_section:
        fields["yt_title_1"] = _extract_md_field(yt_section, r'\*\*عنوان الفيديو الأول:\*\*')
        fields["yt_title_2"] = _extract_md_field(yt_section, r'\*\*عنوان الفيديو الثاني:\*\*')
        fields["yt_desc_1"] = _extract_md_field(yt_section, r'\*\*وصف الفيديو الأول:\*\*')
        fields["yt_desc_2"] = _extract_md_field(yt_section, r'\*\*وصف الفيديو الثاني:\*\*')
        fields["yt_thumb_1"] = _extract_md_field(yt_section, r'\*\*جملة الصورة المصغرة للفيديو الأول:\*\*')
        fields["yt_thumb_2"] = _extract_md_field(yt_section, r'\*\*جملة الصورة المصغرة للفيديو الثاني:\*\*')
        fields["yt_keywords"] = _extract_md_field(yt_section, r'\*\*الكلمات المفتاحية:\*\*')

    # === TikTok Section ===
    if tt_section:
        fields["tt_title"] = _extract_md_field(tt_section, r'\*\*العنوان:\*\*')
        fields["tt_desc"] = _extract_md_field(tt_section, r'\*\*الوصف:\*\*')
        fields["tt_screen"] = _extract_md_field(tt_section, r'\*\*جملة الشاشة:\*\*')

    # === Facebook Section ===
    if fb_section:
        fields["fb_title"] = _extract_md_field(fb_section, r'\*\*العنوان:\*\*')
        fields["fb_desc"] = _extract_md_field(fb_section, r'\*\*الوصف:\*\*')
        fields["fb_thumb"] = _extract_md_field(fb_section, r'\*\*جملة الصورة المصغرة:\*\*')
        fields["fb_keywords"] = _extract_md_field(fb_section, r'\*\*الكلمات المفتاحية:\*\*')

    # === Translation Section ===
    if tr_section:
        fields["tr_en_title"] = _extract_translation_field(tr_section, "الانجليزية", "Title|title")
        fields["tr_en_desc"] = _extract_translation_field(tr_section, "الانجليزية", "Description|description")
        fields["tr_fr_title"] = _extract_translation_field(tr_section, "الفرنسية", "Titre|titre")
        fields["tr_fr_desc"] = _extract_translation_field(tr_section, "الفرنسية", "Description|description")
        fields["tr_es_title"] = _extract_translation_field(tr_section, "الأسبانية", r"T[ií]tulo|titulo")
        fields["tr_es_desc"] = _extract_translation_field(tr_section, "الأسبانية", r"Descripci[oó]n|descripcion")
        fields["tr_de_title"] = _extract_translation_field(tr_section, "الألمانية", "Titel|titel")
        fields["tr_de_desc"] = _extract_translation_field(tr_section, "الألمانية", "Beschreibung|beschreibung")

    return fields


def _extract_md_field(section: str, field_pattern: str) -> str:
    """
    Extract a field value from a markdown section.
    The pattern matches the label, and everything until the next ** label or --- or ### is the value.
    """
    pattern = field_pattern + r'\s*\n(.*?)(?=\n\*\*[^*]|\n---|\n###|\Z)'
    match = re.search(pattern, section, re.DOTALL)
    if match:
        value = match.group(1).strip()
        # Remove trailing --- separator
        value = re.sub(r'\n?---\s*$', '', value).strip()
        return value
    return ""


def _extract_translation_field(section: str, lang_marker: str, field_label: str) -> str:
    """
    Extract a translation field (Title/Description) for a specific language.
    """
    lang_pattern = rf'الترجمة\s+{lang_marker}:\*\*\s*\n(.*?)(?=\n\*\*\d+-\s*الترجمة|\Z)'
    lang_match = re.search(lang_pattern, section, re.DOTALL)
    if not lang_match:
        return ""

    lang_block = lang_match.group(1)

    field_pattern = rf'\*\*(?:{field_label}):\*\*\s*(.*?)(?=\n\*\*(?:{_next_field_pattern(field_label)})|\n\*\*\d+-|\Z)'
    field_match = re.search(field_pattern, lang_block, re.DOTALL | re.IGNORECASE)
    if field_match:
        value = field_match.group(1).strip()
        return value

    return ""


def _next_field_pattern(current_label: str) -> str:
    """Return a pattern for the next field after the current one in a translation block."""
    if "title" in current_label.lower() or "titre" in current_label.lower() or "titulo" in current_label.lower() or "titel" in current_label.lower():
        return r"Description|description|Beschreibung|beschreibung|Descripci[oó]n|descripcion"
    return r"[A-Z]"
