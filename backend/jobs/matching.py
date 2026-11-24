"""Conservative local duplicate suggestions, never automatic merges."""

import re
import unicodedata
from collections import Counter
from hashlib import sha256
from sqlite3 import Connection

_ANONYMOUS_COMPANY = re.compile(
    r"(?:某.*|.{1,12}某.*(?:公司|企业|客户|集团|单位)|x{2,}.*|"
    r"不(?:详|明|便?(?:公开|透露|披露))|未知|未(?:知|公开|透露|披露|定)|"
    r"匿名(?:公司|企业|客户|用人单位)?|保密(?:公司|企业|客户)?|客户|客户公司|"
    r"(?:实际)?(?:客户|用人单位)(?:保密|未知|不详|未公开|未透露|未披露)|"
    r"(?:头部|知名|行业领先|保密|匿名|世界500强).*(?:公司|企业|客户|集团)|"
    r"(?:上市|互联网|大型|外资|国内|国际)(?:公司|企业|客户|集团)|"
    r"companyna|na|none|(?:unknown|undisclosed|confidential|anonymous|stealth)"
    r"(?:company|client|employer)?)"
)
_COMPANY_SUFFIX = re.compile(
    r"(?:股份有限公司|有限责任公司|有限公司|集团公司|inc|ltd|limited|llc)$"
)


def normalize(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKC", value).casefold() if char.isalnum()
    )


def role_identity(role: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKC", role).casefold()
        if char.isalnum() or char in "+#"
    )


def company_identity(name: str) -> str:
    identity = normalize(name)
    if not identity or _ANONYMOUS_COMPANY.fullmatch(identity):
        return ""
    without_suffix = _COMPANY_SUFFIX.sub("", identity)
    if not without_suffix or _ANONYMOUS_COMPANY.fullmatch(without_suffix):
        return ""
    return without_suffix


def jd_hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def confirm_agency(company: str, agency: str) -> bool:
    company_key = normalize(company)
    agency_key = normalize(agency)
    if not company_key or not agency_key:
        return False
    return company_key == agency_key or (
        _COMPANY_SUFFIX.sub("", company_key) == _COMPANY_SUFFIX.sub("", agency_key)
    )


def field_candidates(conn: Connection, company: str, role: str) -> list[int]:
    company_key, role_key = company_identity(company), role_identity(role)
    if not company_key or not role_key:
        return []
    return [
        row["id"]
        for row in conn.execute(
            """SELECT id FROM jobs WHERE company_key = ? AND role_key = ?
               ORDER BY id DESC LIMIT 8""",
            (company_key, role_key),
        )
    ]


def _trigrams(text: str) -> Counter[str]:
    return Counter(text[index : index + 3] for index in range(len(text) - 2))


def text_candidates(conn: Connection, jd_key: str, raw_jd: str) -> list[int]:
    exact = [
        row["job_id"]
        for row in conn.execute(
            """SELECT DISTINCT job_id FROM encounters WHERE jd_hash = ?
               ORDER BY job_id DESC LIMIT 8""",
            (jd_key,),
        )
    ]
    normalized = normalize(raw_jd)
    if len(normalized) < 80 or len(exact) == 8:
        return exact
    grams = _trigrams(normalized)
    fuzzy: dict[int, float] = {}
    for row in conn.execute(
        """SELECT DISTINCT job_id, jd_normalized FROM encounters
           WHERE jd_length BETWEEN ? AND ? AND jd_hash <> ?""",
        (len(normalized) * 0.9, len(normalized) / 0.9, jd_key),
    ):
        job_id = row["job_id"]
        if job_id in exact:
            continue
        other_text = row["jd_normalized"]
        intersection = grams & _trigrams(other_text)
        score = 2 * intersection.total() / (len(normalized) + len(other_text) - 4)
        if score >= 0.94:
            fuzzy[job_id] = max(score, fuzzy.get(job_id, 0))
    return (exact + sorted(fuzzy, key=lambda job_id: (-fuzzy[job_id], -job_id)))[:8]
