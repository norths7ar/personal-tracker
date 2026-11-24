"""Durable job records, drafts, and short SQLite claims for model work."""

import json
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from sqlite3 import Connection, Row
from typing import Literal
from uuid import uuid4

from backend.db import connect, hash_payload
from backend.jobs import matching
from backend.jobs.docx import clean_filename
from backend.jobs.models import (
    Analysis,
    Encounter,
    EncounterInput,
    Intake,
    IntakeCreate,
    IntakeSave,
    JobDetail,
    JobFields,
    JobStatus,
    JobSummary,
    JobUpdate,
    MatchLevel,
    MatchSource,
    Message,
    Profile,
    ProfileWrite,
    UnfinishedQuestion,
)
from backend.paths import jobs_database_path

_CLAIM_GRACE = 300  # Normal requests finish sooner; this also bounds crash recovery.
_INTERRUPTED = "请求中断，已保留原文，可以重试"
_ANALYSIS_INTERRUPTED = "分析中断，岗位与 JD 已保存，可以重试"
_EMPTY_PROFILE = Profile(
    resume_text="", supplemental_notes="", imported_filename=None, imported_at=None, updated_at=None
)
_FIELD_NAMES = tuple(JobFields.model_fields)


class NotFound(ValueError):
    pass


class Conflict(ValueError):
    pass


@dataclass(frozen=True)
class Claim:
    scope: Literal["intakes", "operations"]
    id: int
    token: str


@dataclass(frozen=True)
class ModelOperation:
    job: JobDetail
    profile: Profile
    encounter: Encounter | None
    greeting_enabled: bool
    question: str | None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def init_db() -> None:
    with closing(connect(jobs_database_path())) as conn:
        conn.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))


@contextmanager
def _connection(*, write: bool = False) -> Iterator[Connection]:
    with closing(connect(jobs_database_path(), readonly=not write)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield conn


def _row(conn: Connection, table: Literal["jobs", "intakes", "operations"], ident: int) -> Row:
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (ident,)).fetchone()
    if row is None:
        raise NotFound("找不到这条求职记录")
    return row


def _profile(conn: Connection) -> Profile:
    row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
    return Profile.model_validate(dict(row)) if row else _EMPTY_PROFILE


def get_profile() -> Profile:
    with _connection() as conn:
        return _profile(conn)


def profile_fingerprint(profile: Profile) -> str:
    return hash_payload([profile.resume_text, profile.supplemental_notes])


def save_profile(body: ProfileWrite) -> Profile:
    with _connection(write=True) as conn:
        previous = _profile(conn)
        now = _now()
        filename, imported_at = previous.imported_filename, previous.imported_at
        if "imported_filename" in body.model_fields_set:
            filename = clean_filename(body.imported_filename) if body.imported_filename else None
            imported_at = now if filename else None
        if (
            previous.resume_text == body.resume_text
            and previous.supplemental_notes == body.supplemental_notes
            and previous.imported_filename == filename
            and previous.imported_at == imported_at
        ):
            return previous
        conn.execute(
            """INSERT INTO profile
               (id, resume_text, supplemental_notes, imported_filename, imported_at, updated_at)
               VALUES (1, ?, ?, ?, ?, ?)
               ON CONFLICT (id) DO UPDATE SET resume_text = excluded.resume_text,
                 supplemental_notes = excluded.supplemental_notes,
                 imported_filename = excluded.imported_filename,
                 imported_at = excluded.imported_at, updated_at = excluded.updated_at""",
            (body.resume_text, body.supplemental_notes, filename, imported_at, now),
        )
        return _profile(conn)


_SUMMARY_SQL = """
SELECT jobs.*,
    (SELECT count(*) FROM encounters WHERE encounters.job_id = jobs.id) AS encounter_count,
    (SELECT max(date) FROM encounters WHERE encounters.job_id = jobs.id) AS latest_encounter_date,
    latest.id AS analysis_id, latest.result_json AS analysis_json,
    latest.completed_at AS analysis_created_at, latest.profile_fingerprint,
    attempt.status AS attempt_status, attempt.error AS attempt_error,
    attempt.expires_at AS attempt_expires_at
FROM jobs
LEFT JOIN operations AS latest ON latest.id = (
    SELECT id FROM operations
    WHERE job_id = jobs.id AND kind = 'analysis' AND status = 'complete'
    ORDER BY id DESC LIMIT 1
)
LEFT JOIN operations AS attempt ON attempt.id = (
    SELECT id FROM operations WHERE job_id = jobs.id AND kind = 'analysis'
    ORDER BY id DESC LIMIT 1
)
"""


def _summary(row: Row, fingerprint: str) -> JobSummary:
    analysis = None
    if row["analysis_id"] is not None:
        analysis = Analysis(
            id=row["analysis_id"],
            created_at=row["analysis_created_at"],
            **json.loads(row["analysis_json"]),
        )
    status = row["attempt_status"] or "none"
    error = row["attempt_error"] or ""
    if status == "pending" and row["attempt_expires_at"] <= time.time():
        status, error = "failed", _ANALYSIS_INTERRUPTED
    return JobSummary(
        **{field: row[field] for field in _FIELD_NAMES},
        id=row["id"],
        encounter_count=row["encounter_count"],
        latest_encounter_date=row["latest_encounter_date"],
        latest_analysis=analysis,
        analysis_status=status,
        analysis_error=error,
        analysis_stale=analysis is not None and fingerprint != row["profile_fingerprint"],
    )


def _contains_folded(text: str | None, needle: str) -> bool:
    return text is not None and needle in text.casefold()


def list_jobs(
    *,
    q: str = "",
    status: JobStatus | None = None,
    platform: str | None = None,
    city: str | None = None,
    is_headhunter: bool | None = None,
    match_level: MatchLevel | None = None,
) -> list[JobSummary]:
    filters = []
    parameters = {}
    if q := q.strip().casefold():
        filters.append(
            """(contains_folded(jobs.company, :q) OR contains_folded(jobs.headhunter_agency, :q)
                OR contains_folded(jobs.role, :q) OR EXISTS (
                    SELECT 1 FROM encounters
                    WHERE job_id = jobs.id AND (contains_folded(contact, :q)
                       OR contains_folded(raw_jd, :q))
                ) OR EXISTS (
                    SELECT 1 FROM operations
                    WHERE job_id = jobs.id AND kind = 'analysis' AND status = 'complete'
                      AND (contains_folded(json_extract(result_json, '$.verdict'), :q)
                         OR contains_folded(json_extract(result_json, '$.analysis_markdown'), :q))
                ))"""
        )
        parameters["q"] = q
    for column, value in (("status", status), ("is_headhunter", is_headhunter)):
        if value is not None:
            filters.append(f"jobs.{column} = :{column}")
            parameters[column] = value
    if city and (city := city.strip().casefold()):
        filters.append("contains_folded(jobs.city, :city)")
        parameters["city"] = city
    if platform and (platform := platform.strip().casefold()):
        filters.append(
            """EXISTS (SELECT 1 FROM encounters
               WHERE job_id = jobs.id AND contains_folded(platform, :platform))"""
        )
        parameters["platform"] = platform
    if match_level is not None:
        filters.append("json_extract(latest.result_json, '$.match_level') = :match_level")
        parameters["match_level"] = match_level
    clause = " WHERE " + " AND ".join(filters) if filters else ""
    with _connection() as conn:
        conn.create_function("contains_folded", 2, _contains_folded, deterministic=True)
        fingerprint = profile_fingerprint(_profile(conn))
        rows = conn.execute(
            _SUMMARY_SQL + clause + " ORDER BY latest_encounter_date DESC, jobs.id DESC", parameters
        )
        return [_summary(row, fingerprint) for row in rows]


def _job_detail(conn: Connection, job_id: int) -> JobDetail:
    row = conn.execute(_SUMMARY_SQL + " WHERE jobs.id = ?", (job_id,)).fetchone()
    if row is None:
        raise NotFound("找不到这个岗位")
    summary = _summary(row, profile_fingerprint(_profile(conn)))
    encounters = [
        Encounter.model_validate(dict(encounter))
        for encounter in conn.execute(
            """SELECT id, date, platform, contact, salary, raw_jd, notes
               FROM encounters WHERE job_id = ? ORDER BY date DESC, id DESC""",
            (job_id,),
        )
    ]
    analyses = []
    messages = []
    for record in conn.execute(
        """SELECT id, kind, question, result_json, created_at, completed_at
           FROM operations
           WHERE job_id = ? AND status = 'complete'
           ORDER BY completed_at, id""",
        (job_id,),
    ):
        result = json.loads(record["result_json"])
        if record["kind"] == "analysis":
            analyses.append(Analysis(id=record["id"], created_at=record["completed_at"], **result))
        else:
            messages.extend(
                (
                    Message(
                        id=record["id"] * 2,
                        role="user",
                        content=record["question"],
                        created_at=record["created_at"],
                    ),
                    Message(
                        id=record["id"] * 2 + 1,
                        role="assistant",
                        content=result,
                        created_at=record["completed_at"],
                    ),
                )
            )
    unresolved = []
    for question in conn.execute(
        """SELECT request_key, question, status, error, expires_at FROM operations
           WHERE job_id = ? AND kind = 'question' AND status <> 'complete'
           ORDER BY created_at, id""",
        (job_id,),
    ):
        status, error = question["status"], question["error"]
        if status == "pending" and question["expires_at"] <= time.time():
            status, error = "failed", _INTERRUPTED
        unresolved.append(
            UnfinishedQuestion(
                request_id=question["request_key"],
                question=question["question"],
                status=status,
                error=error,
            )
        )
    return JobDetail(
        **summary.model_dump(),
        encounters=encounters,
        analyses=analyses[::-1],
        messages=messages,
        unfinished_questions=unresolved,
    )


def get_job(job_id: int) -> JobDetail:
    with _connection() as conn:
        return _job_detail(conn, job_id)


def _job_fields(fields: JobFields) -> dict:
    if matching.confirm_agency(fields.company, fields.headhunter_agency):
        raise ValueError("实际用人单位不能与猎头机构相同；客户未公开时留空")
    data = fields.model_dump()
    data["company_key"] = matching.company_identity(fields.company)
    data["role_key"] = matching.role_identity(fields.role)
    return data


def update_job(job_id: int, body: JobUpdate) -> JobDetail:
    with _connection(write=True) as conn:
        row = _row(conn, "jobs", job_id)
        fields = JobFields.model_validate(
            {**{name: row[name] for name in _FIELD_NAMES}, **body.model_dump(exclude_unset=True)}
        )
        data = _job_fields(fields)
        updates = ", ".join(f"{name} = :{name}" for name in data)
        conn.execute(f"UPDATE jobs SET {updates} WHERE id = :id", {**data, "id": job_id})
        return _job_detail(conn, job_id)


def _intake_summary(conn: Connection, row: Row) -> Intake:
    candidate_ids = json.loads(row["candidate_ids_json"])
    candidates = []
    if candidate_ids:
        fingerprint = profile_fingerprint(_profile(conn))
        marks = ",".join("?" for _ in candidate_ids)
        found = {
            candidate["id"]: _summary(candidate, fingerprint)
            for candidate in conn.execute(
                _SUMMARY_SQL + f" WHERE jobs.id IN ({marks})", candidate_ids
            )
        }
        candidates = [found[ident] for ident in candidate_ids if ident in found]
    status, error = row["status"], row["error"]
    if status == "pending" and row["expires_at"] <= time.time():
        status, error = "failed", _INTERRUPTED
    return Intake(
        id=row["id"],
        encounter=EncounterInput.model_validate_json(row["encounter_json"]),
        greeting_enabled=bool(row["greeting_enabled"]),
        fields=JobFields.model_validate_json(row["fields_json"]) if row["fields_json"] else None,
        candidates=candidates,
        match_source=row["match_source"],
        status=status,
        error=error,
        job_id=row["job_id"],
    )


def get_intake(intake_id: int) -> Intake:
    with _connection() as conn:
        return _intake_summary(conn, _row(conn, "intakes", intake_id))


def list_intakes() -> list[Intake]:
    with _connection() as conn:
        return [
            _intake_summary(conn, row)
            for row in conn.execute(
                "SELECT * FROM intakes WHERE status <> 'saved' ORDER BY id DESC"
            )
        ]


def discard_intake(intake_id: int) -> None:
    with _connection(write=True) as conn:
        removed = conn.execute(
            """DELETE FROM intakes WHERE id = ? AND status <> 'saved'
               RETURNING id, request_id""",
            (intake_id,),
        ).fetchone()
        if removed is not None:
            conn.execute(
                "INSERT INTO discarded_intakes(id, request_id) VALUES (?, ?)",
                (removed["id"], removed["request_id"]),
            )
        elif conn.execute("SELECT 1 FROM intakes WHERE id = ?", (intake_id,)).fetchone():
            raise Conflict("此录入已经保存，不能作为待确认草稿丢弃")


def _new_claim(scope: Literal["intakes", "operations"], ident: int) -> Claim:
    return Claim(scope, ident, uuid4().hex)


def _expires() -> float:
    return time.time() + _CLAIM_GRACE


def create_intake(body: IntakeCreate) -> tuple[int, Claim | None]:
    data = body.model_dump(mode="json", exclude={"request_id", "greeting_enabled"})
    signature = hash_payload({**data, "greeting_enabled": body.greeting_enabled})
    greeting = body.greeting_enabled
    if greeting is None:
        greeting = matching.normalize(body.platform) == "boss直聘"
    request_id = str(body.request_id)
    token = uuid4().hex
    with _connection(write=True) as conn:
        previous = conn.execute(
            "SELECT id, request_hash FROM intakes WHERE request_id = ?", (request_id,)
        ).fetchone()
        if previous:
            if previous["request_hash"] != signature:
                raise Conflict("同一录入请求已用于不同内容")
            return previous["id"], None
        if conn.execute(
            "SELECT 1 FROM discarded_intakes WHERE request_id = ?", (request_id,)
        ).fetchone():
            raise Conflict("此录入已丢弃，若要再次录入，请重新提交")
        created = conn.execute(
            """INSERT INTO intakes (
                id, request_id, request_hash, encounter_json, jd_hash, greeting_enabled, status,
                claim_token, expires_at
            ) VALUES (
                max(coalesce((SELECT max(id) FROM intakes), 0),
                    coalesce((SELECT max(id) FROM discarded_intakes), 0)) + 1,
                ?, ?, ?, ?, ?, 'pending', ?, ?
            ) RETURNING id""",
            (
                request_id,
                signature,
                _json(data),
                matching.jd_hash(matching.normalize(body.raw_jd) or body.raw_jd),
                greeting,
                token,
                _expires(),
            ),
        ).fetchone()
        return created["id"], Claim("intakes", created["id"], token)


def retry_intake(intake_id: int) -> Claim | None:
    claim = _new_claim("intakes", intake_id)
    with _connection(write=True) as conn:
        _row(conn, "intakes", intake_id)
        result = conn.execute(
            """UPDATE intakes SET status = 'pending', error = '', claim_token = ?, expires_at = ?
               WHERE id = ? AND (status = 'failed' OR (status = 'pending' AND expires_at <= ?))""",
            (claim.token, _expires(), intake_id, time.time()),
        )
        return claim if result.rowcount else None


def intake_source(claim: Claim) -> tuple[EncounterInput, str]:
    with _connection() as conn:
        row = _row(conn, "intakes", claim.id)
        return EncounterInput.model_validate_json(row["encounter_json"]), row["jd_hash"]


def text_candidates(jd_key: str, raw_jd: str) -> list[int]:
    with _connection() as conn:
        return matching.text_candidates(conn, jd_key, raw_jd)


def field_candidates(fields: JobFields) -> list[int]:
    with _connection() as conn:
        return matching.field_candidates(conn, fields.company, fields.role)


def finish_intake(
    claim: Claim,
    encounter: EncounterInput,
    *,
    fields: JobFields | None = None,
    candidates: list[int] | None = None,
    match_source: MatchSource = "none",
    error: str = "",
) -> None:
    with _connection(write=True) as conn:
        conn.execute(
            """UPDATE intakes SET status = ?, error = ?, claim_token = NULL, expires_at = NULL,
                 encounter_json = ?, fields_json = ?, candidate_ids_json = ?, match_source = ?
               WHERE id = ? AND status = 'pending' AND claim_token = ?""",
            (
                "failed" if error else "ready",
                error,
                encounter.model_dump_json(),
                fields.model_dump_json() if fields else None,
                _json(candidates or []),
                match_source,
                claim.id,
                claim.token,
            ),
        )


def _reap_operations(conn: Connection, job_id: int) -> None:
    conn.execute(
        """UPDATE operations SET status = 'failed',
             error = CASE kind WHEN 'analysis' THEN ? ELSE ? END,
             claim_token = NULL, expires_at = NULL
           WHERE job_id = ? AND status = 'pending' AND expires_at <= ?""",
        (_ANALYSIS_INTERRUPTED, _INTERRUPTED, job_id, time.time()),
    )


def _new_operation(
    conn: Connection,
    job_id: int,
    kind: Literal["analysis", "question"],
    request_key: str,
    *,
    encounter_id: int | None = None,
    question: str | None = None,
) -> Claim:
    _reap_operations(conn, job_id)
    if conn.execute(
        "SELECT 1 FROM operations WHERE job_id = ? AND status = 'pending'", (job_id,)
    ).fetchone():
        raise Conflict("这个岗位有正在处理的分析或追问，请稍后重试")
    token = uuid4().hex
    row = conn.execute(
        """INSERT INTO operations
           (job_id, kind, request_key, status, claim_token, expires_at, encounter_id, question,
            created_at)
           VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?) RETURNING id""",
        (job_id, kind, request_key, token, _expires(), encounter_id, question, _now()),
    ).fetchone()
    return Claim("operations", row["id"], token)


def save_intake(intake_id: int, body: IntakeSave) -> tuple[int, Claim | None]:
    signature = hash_payload(body.model_dump(mode="json"))
    with _connection(write=True) as conn:
        row = _row(conn, "intakes", intake_id)
        if row["status"] == "saved":
            if row["save_hash"] != signature:
                raise Conflict("该录入已经用另一组选择保存，不能再次保存")
            return row["job_id"], None
        if row["status"] == "pending" and row["expires_at"] > time.time():
            raise Conflict("JD 正在提取，请稍后再保存")

        original = EncounterInput.model_validate_json(row["encounter_json"])
        encounter = body.encounter or original
        if (encounter.raw_jd, encounter.platform) != (original.raw_jd, original.platform):
            raise ValueError("保存时不能更改本次录入的 JD 原文或平台")

        if body.decision == "new_analyze":
            if body.job_id is not None:
                raise ValueError("新建岗位不能指定已有岗位")
            fields = body.fields
            if fields is None and row["fields_json"]:
                fields = JobFields.model_validate_json(row["fields_json"])
            if fields is None:
                raise ValueError("请先补充新岗位的结构化信息")
            data = _job_fields(fields)
            columns = ", ".join(data)
            values = ", ".join(f":{name}" for name in data)
            job = conn.execute(
                f"INSERT INTO jobs ({columns}) VALUES ({values}) RETURNING id", data
            ).fetchone()
            job_id = job["id"]
        else:
            job_id = body.job_id
            if job_id is None or job_id not in json.loads(row["candidate_ids_json"]):
                raise ValueError("请选择本次录入识别出的已有岗位")
            if (
                body.decision == "merge_reuse"
                and not conn.execute(
                    """SELECT 1 FROM operations
                   WHERE job_id = ? AND kind = 'analysis' AND status = 'complete'""",
                    (job_id,),
                ).fetchone()
            ):
                raise ValueError("该岗位没有可复用的分析，请选择重新分析")

        jd = matching.normalize(encounter.raw_jd)
        inserted = conn.execute(
            """INSERT INTO encounters (
               job_id, intake_id, date, platform, contact, salary, raw_jd, notes,
               jd_hash, jd_normalized, jd_length, greeting_enabled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (
                job_id,
                intake_id,
                encounter.date.isoformat(),
                encounter.platform,
                encounter.contact,
                encounter.salary,
                encounter.raw_jd,
                encounter.notes,
                row["jd_hash"],
                jd,
                len(jd),
                row["greeting_enabled"],
            ),
        ).fetchone()
        conn.execute(
            """UPDATE intakes SET status = 'saved', job_id = ?, save_hash = ?, error = '',
                 claim_token = NULL, expires_at = NULL, encounter_json = ?
               WHERE id = ?""",
            (job_id, signature, encounter.model_dump_json(), intake_id),
        )
        claim = None
        if body.decision != "merge_reuse":
            claim = _new_operation(
                conn, job_id, "analysis", f"intake:{intake_id}", encounter_id=inserted["id"]
            )
        return job_id, claim


def start_analysis(job_id: int, request_id: str) -> Claim | None:
    with _connection(write=True) as conn:
        _row(conn, "jobs", job_id)
        if conn.execute(
            """SELECT 1 FROM operations
               WHERE job_id = ? AND kind = 'analysis' AND request_key = ?""",
            (job_id, request_id),
        ).fetchone():
            return None
        _reap_operations(conn, job_id)
        previous = conn.execute(
            """SELECT status, encounter_id FROM operations WHERE job_id = ? AND kind = 'analysis'
               ORDER BY id DESC LIMIT 1""",
            (job_id,),
        ).fetchone()
        if previous is not None and previous["status"] == "failed":
            encounter_id = previous["encounter_id"]
        else:
            encounter = conn.execute(
                "SELECT id FROM encounters WHERE job_id = ? ORDER BY date DESC, id DESC LIMIT 1",
                (job_id,),
            ).fetchone()
            encounter_id = encounter["id"]
        return _new_operation(conn, job_id, "analysis", request_id, encounter_id=encounter_id)


def start_question(job_id: int, request_id: str, question: str) -> Claim | None:
    with _connection(write=True) as conn:
        _row(conn, "jobs", job_id)
        _reap_operations(conn, job_id)
        existing = conn.execute(
            """SELECT id, question, status FROM operations
               WHERE job_id = ? AND kind = 'question' AND request_key = ?""",
            (job_id, request_id),
        ).fetchone()
        if existing is None:
            return _new_operation(conn, job_id, "question", request_id, question=question)
        if existing["question"] != question:
            raise Conflict("同一追问请求已用于不同内容")
        if existing["status"] == "complete":
            return None
        if conn.execute(
            "SELECT 1 FROM operations WHERE job_id = ? AND status = 'pending'", (job_id,)
        ).fetchone():
            raise Conflict("这个岗位有正在处理的分析或追问，请稍后重试")
        claim = _new_claim("operations", existing["id"])
        conn.execute(
            """UPDATE operations SET status = 'pending', error = '', claim_token = ?, expires_at = ?,
                 created_at = ?
               WHERE id = ?""",
            (claim.token, _expires(), _now(), claim.id),
        )
        return claim


def renew_claim(claim: Claim, timeout: float) -> bool:
    expiration = time.time() + max(_CLAIM_GRACE, timeout * 4 + 10)
    with _connection(write=True) as conn:
        result = conn.execute(
            f"UPDATE {claim.scope} SET expires_at = ? WHERE id = ? AND claim_token = ?",
            (expiration, claim.id, claim.token),
        )
        return bool(result.rowcount)


def operation_input(claim: Claim) -> ModelOperation:
    with _connection() as conn:
        row = _row(conn, "operations", claim.id)
        job = _job_detail(conn, row["job_id"])
        profile = _profile(conn)
        encounter = None
        greeting_enabled = False
        if row["encounter_id"] is not None:
            encounter = next(item for item in job.encounters if item.id == row["encounter_id"])
            greeting_enabled = bool(
                conn.execute(
                    "SELECT greeting_enabled FROM encounters WHERE id = ?", (encounter.id,)
                ).fetchone()[0]
            )
        return ModelOperation(job, profile, encounter, greeting_enabled, row["question"])


def finish_operation(
    claim: Claim,
    *,
    result: dict | str | None = None,
    fingerprint: str | None = None,
    error: str = "",
) -> bool:
    with _connection(write=True) as conn:
        updated = conn.execute(
            """UPDATE operations SET status = ?, error = ?, claim_token = NULL, expires_at = NULL,
                 profile_fingerprint = ?, result_json = ?, completed_at = ?
               WHERE id = ? AND status = 'pending' AND claim_token = ?""",
            (
                "failed" if error else "complete",
                error,
                fingerprint,
                _json(result) if not error else None,
                _now() if not error else None,
                claim.id,
                claim.token,
            ),
        )
        return bool(updated.rowcount)


def context_input(job_id: int) -> tuple[Profile, JobDetail]:
    with _connection() as conn:
        return _profile(conn), _job_detail(conn, job_id)
