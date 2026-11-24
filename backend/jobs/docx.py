"""Extract editable plain text from the main body of a Word document."""

from io import BytesIO
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from backend.jobs.models import MAX_RESUME_LENGTH

MAX_DOCX_BYTES = 8 * 1024 * 1024
_MAX_XML_BYTES = 16 * 1024 * 1024
_WORD_NAMESPACES = {
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "http://purl.oclc.org/ooxml/wordprocessingml/main",
}


def clean_filename(filename: str) -> str:
    name = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name.lower().endswith(".docx") or not 5 < len(name) <= 255 or not name.isprintable():
        raise ValueError("请选择有效的 .docx 文件")
    return name


def extract_text(content: bytes) -> str:
    if not content or len(content) > MAX_DOCX_BYTES:
        raise ValueError("Word 文件为空或超过 8 MiB")
    try:
        with ZipFile(BytesIO(content)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > _MAX_XML_BYTES:
                raise ValueError("Word 文档正文过大")
            with archive.open(info) as xml_file:
                raw_xml = xml_file.read(_MAX_XML_BYTES + 1)
        if len(raw_xml) > _MAX_XML_BYTES:
            raise ValueError("Word 文档正文过大")
        encoding = "utf-16" if raw_xml.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        xml = raw_xml.decode(encoding)
        if "<!DOCTYPE" in xml:
            raise ValueError("Word 文档正文不能包含 DTD")
        root = ElementTree.fromstring(xml)
    except (
        BadZipFile,
        KeyError,
        OSError,
        RuntimeError,
        EOFError,
        UnicodeError,
        ElementTree.ParseError,
    ) as exc:
        raise ValueError("无法读取 Word 文档正文，请使用未加密的 .docx 文件") from exc

    namespace = root.tag.removeprefix("{").removesuffix("}document")
    if namespace not in _WORD_NAMESPACES:
        raise ValueError("文件没有有效的 Word 文档正文")
    tag = f"{{{namespace}}}"
    body = root.find(f"{tag}body")
    if body is None:
        raise ValueError("文件没有有效的 Word 文档正文")
    result = "\n".join(_block_text(body, tag)).strip()
    if not result:
        raise ValueError("Word 文档未包含可导入的正文文字")
    if len(result) > MAX_RESUME_LENGTH:
        raise ValueError("简历正文超过长度限制")
    return result


def _block_text(parent: ElementTree.Element, tag: str, depth: int = 0) -> list[str]:
    if depth > 64:
        raise ValueError("Word 文档正文嵌套过深")
    lines = []
    for item in parent:
        if item.tag == f"{tag}p":
            lines.append(_paragraph_text(item, tag))
        elif item.tag == f"{tag}tbl":
            for row in item.findall(f"{tag}tr"):
                cells = (
                    " / ".join(_block_text(cell, tag, depth + 1))
                    for cell in row.findall(f"{tag}tc")
                )
                lines.append(" | ".join(cells))
        elif item.tag == f"{tag}sdt":
            content = item.find(f"{tag}sdtContent")
            if content is not None:
                lines.extend(_block_text(content, tag, depth + 1))
    return lines


def _paragraph_text(paragraph: ElementTree.Element, tag: str) -> str:
    tokens = []
    for node in paragraph.iter():
        if node.tag == f"{tag}t":
            tokens.append(node.text or "")
        elif node.tag == f"{tag}tab":
            tokens.append("\t")
        elif node.tag in {f"{tag}br", f"{tag}cr"}:
            tokens.append("\n")
    return "".join(tokens)
