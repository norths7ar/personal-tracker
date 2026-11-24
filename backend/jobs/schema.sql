CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    resume_text TEXT NOT NULL,
    supplemental_notes TEXT NOT NULL,
    imported_filename TEXT,
    imported_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    company TEXT NOT NULL,
    company_key TEXT NOT NULL,
    role TEXT NOT NULL CHECK(length(role) > 0),
    role_key TEXT NOT NULL,
    city TEXT NOT NULL,
    salary TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('待决定', '已联系', '已跳过')),
    notes TEXT NOT NULL,
    is_headhunter INTEGER NOT NULL CHECK(is_headhunter IN (0, 1)),
    headhunter_agency TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS jobs_identity_idx ON jobs(company_key, role_key);

CREATE TABLE IF NOT EXISTS intakes (
    id INTEGER PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    request_hash TEXT NOT NULL,
    encounter_json TEXT NOT NULL,
    jd_hash TEXT NOT NULL,
    greeting_enabled INTEGER NOT NULL CHECK(greeting_enabled IN (0, 1)),
    fields_json TEXT,
    candidate_ids_json TEXT NOT NULL DEFAULT '[]',
    match_source TEXT NOT NULL DEFAULT 'none' CHECK(match_source IN ('none', 'text', 'fields')),
    status TEXT NOT NULL CHECK(status IN ('pending', 'ready', 'failed', 'saved')),
    error TEXT NOT NULL DEFAULT '',
    claim_token TEXT,
    expires_at REAL,
    job_id INTEGER REFERENCES jobs(id),
    save_hash TEXT,
    CHECK((status = 'pending') = (claim_token IS NOT NULL AND expires_at IS NOT NULL)),
    CHECK((status = 'saved') = (job_id IS NOT NULL AND save_hash IS NOT NULL))
);

-- Reserve discarded identifiers so a stale retry cannot restore or address another draft.
CREATE TABLE IF NOT EXISTS discarded_intakes (
    id INTEGER PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS encounters (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    intake_id INTEGER NOT NULL UNIQUE REFERENCES intakes(id),
    date TEXT NOT NULL,
    platform TEXT NOT NULL,
    contact TEXT NOT NULL,
    salary TEXT NOT NULL,
    raw_jd TEXT NOT NULL,
    notes TEXT NOT NULL,
    jd_hash TEXT NOT NULL,
    jd_normalized TEXT NOT NULL,
    jd_length INTEGER NOT NULL,
    greeting_enabled INTEGER NOT NULL CHECK(greeting_enabled IN (0, 1)),
    UNIQUE(id, job_id)
);

CREATE INDEX IF NOT EXISTS encounter_by_job_idx ON encounters(job_id, date DESC, id DESC);
CREATE INDEX IF NOT EXISTS encounter_jd_hash_idx ON encounters(jd_hash);
CREATE INDEX IF NOT EXISTS encounter_jd_length_idx ON encounters(jd_length);

CREATE TABLE IF NOT EXISTS operations (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    kind TEXT NOT NULL CHECK(kind IN ('analysis', 'question')),
    request_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'complete', 'failed')),
    error TEXT NOT NULL DEFAULT '',
    claim_token TEXT,
    expires_at REAL,
    encounter_id INTEGER,
    profile_fingerprint TEXT,
    result_json TEXT,
    question TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (job_id, kind, request_key),
    FOREIGN KEY(encounter_id, job_id) REFERENCES encounters(id, job_id),
    CHECK((status = 'pending') = (claim_token IS NOT NULL AND expires_at IS NOT NULL)),
    CHECK((kind = 'analysis') = (encounter_id IS NOT NULL)),
    CHECK((kind = 'question') = (question IS NOT NULL)),
    CHECK((status = 'complete') = (result_json IS NOT NULL AND completed_at IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS one_pending_operation_idx
ON operations(job_id) WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS operation_history_idx ON operations(job_id, kind, status, id DESC);
