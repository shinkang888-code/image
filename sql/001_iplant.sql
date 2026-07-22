-- Lexi IPlant Neon schema
-- Product: lexiipplant | Copyright DB edits: steven8kay

CREATE TABLE IF NOT EXISTS agents (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  last_seen     TIMESTAMPTZ,
  comfy_ok      BOOLEAN DEFAULT FALSE,
  ipplant_path  TEXT,
  detail        TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS jobs (
  id            TEXT PRIMARY KEY,
  type          TEXT NOT NULL,          -- generate | doctor | sync
  payload       JSONB NOT NULL DEFAULT '{}',
  status        TEXT NOT NULL DEFAULT 'pending',  -- pending|running|done|failed|cancelled
  agent_id      TEXT,
  error         TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  started_at    TIMESTAMPTZ,
  finished_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS jobs_status_created_idx ON jobs (status, created_at);

CREATE TABLE IF NOT EXISTS assets (
  id              TEXT PRIMARY KEY,
  prompt_id       TEXT NOT NULL,
  category        TEXT NOT NULL,
  subcategory     TEXT NOT NULL,
  tag             TEXT,
  seed            INT NOT NULL DEFAULT 0,
  width           INT,
  height          INT,
  bytes_webp      INT,
  local_path      TEXT,
  drive_file_id   TEXT,
  share_url       TEXT,
  sha256          TEXT,
  prompt_full     TEXT,
  negative        TEXT,
  iplant_line     TEXT,
  copyright_holder TEXT DEFAULT 'steven8kay',
  schema_json     JSONB,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS assets_cat_idx ON assets (category, subcategory);
CREATE INDEX IF NOT EXISTS assets_created_idx ON assets (created_at DESC);

CREATE TABLE IF NOT EXISTS events (
  id          BIGSERIAL PRIMARY KEY,
  kind        TEXT NOT NULL DEFAULT 'info',
  message     TEXT NOT NULL,
  job_id      TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE VIEW category_stats AS
SELECT category, subcategory, COUNT(*)::INT AS count,
       COALESCE(SUM(bytes_webp), 0)::BIGINT AS bytes
FROM assets
GROUP BY category, subcategory;
