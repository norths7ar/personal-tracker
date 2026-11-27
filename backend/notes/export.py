"""Chronological Markdown and minimal OOXML (.docx) export for personal notes."""

from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

_CONTENT_TYPES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""

_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""


def _format_event_date(entry: dict) -> str:
    start = str(entry["start_date"])
    end = str(entry["end_date"])
    return start if start == end else f"{start} 至 {end}"


def _chronological_sort_key(item: dict) -> tuple[str, str, int]:
    event_dates = item.get("event_dates") or []
    anchor = (
        min(str(entry["start_date"]) for entry in event_dates)
        if event_dates
        else str(item["recorded_date"])
    )
    return anchor, str(item["recorded_date"]), int(item["id"])


def _note_heading(item: dict) -> str:
    title = str(item.get("title") or "").strip()
    if title:
        return title
    event_dates = item.get("event_dates") or []
    anchor = (
        min(str(entry["start_date"]) for entry in event_dates)
        if event_dates
        else str(item["recorded_date"])
    )
    return f"{anchor} 日记"


def _note_meta(item: dict) -> str:
    parts = [f"记录日期：{item['recorded_date']}"]
    event_dates = item.get("event_dates") or []
    if event_dates:
        parts.append("事件日期：" + "、".join(_format_event_date(entry) for entry in event_dates))
    return " · ".join(parts)


def render_markdown(items: list[dict], heading: str) -> str:
    ordered = sorted(items, key=_chronological_sort_key)
    blocks = [f"# {heading}"]
    if not ordered:
        blocks.append("暂无日记。")
        return "\n\n".join(blocks) + "\n"
    for item in ordered:
        blocks.append(f"## {_note_heading(item)}")
        blocks.append(_note_meta(item))
        blocks.append(str(item["content"]).strip())
    return "\n\n".join(blocks) + "\n"


def _paragraph_xml(text: str, *, bold: bool = False, size_half_pts: int | None = None) -> str:
    run_props = []
    if bold:
        run_props.append("<w:b/>")
    if size_half_pts is not None:
        run_props.append(f'<w:sz w:val="{size_half_pts}"/><w:szCs w:val="{size_half_pts}"/>')
    rpr = f"<w:rPr>{''.join(run_props)}</w:rPr>" if run_props else ""
    escaped = escape(text)
    return f'<w:p><w:r>{rpr}<w:t xml:space="preserve">{escaped}</w:t></w:r></w:p>'


def render_docx(items: list[dict], heading: str) -> bytes:
    ordered = sorted(items, key=_chronological_sort_key)
    paragraphs = [_paragraph_xml(heading, bold=True, size_half_pts=32)]
    if not ordered:
        paragraphs.append(_paragraph_xml("暂无日记。"))
    else:
        for item in ordered:
            paragraphs.append(_paragraph_xml(""))
            paragraphs.append(_paragraph_xml(_note_heading(item), bold=True, size_half_pts=26))
            paragraphs.append(_paragraph_xml(_note_meta(item), size_half_pts=18))
            for line in str(item["content"]).splitlines() or [""]:
                paragraphs.append(_paragraph_xml(line))

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(paragraphs)}<w:sectPr/></w:body>"
        "</w:document>"
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES_XML)
        archive.writestr("_rels/.rels", _RELS_XML)
        archive.writestr("word/document.xml", document_xml.encode("utf-8"))
    return buffer.getvalue()
