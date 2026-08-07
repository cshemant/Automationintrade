-- AIT Stock Trigger Intelligence - Cloudflare D1 starter schema
-- Apply only when authenticated watchlists, email alerts and paid entitlements
-- are enabled. The current public feed works without D1.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS companies (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL UNIQUE,
  company_name TEXT NOT NULL,
  isin TEXT,
  slug TEXT NOT NULL UNIQUE,
  sector TEXT,
  market_cap_band TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  company_id INTEGER NOT NULL,
  exchange_announcement_id TEXT,
  event_type TEXT NOT NULL,
  direction TEXT NOT NULL DEFAULT 'NEUTRAL',
  headline TEXT NOT NULL,
  fact_summary TEXT NOT NULL,
  why_it_matters TEXT,
  risks_unknowns TEXT,
  impact_score INTEGER NOT NULL DEFAULT 0 CHECK (impact_score BETWEEN 0 AND 100),
  confidence_score INTEGER NOT NULL DEFAULT 0 CHECK (confidence_score BETWEEN 0 AND 100),
  source_url TEXT NOT NULL,
  source_published_at TEXT,
  fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  rule_version TEXT,
  model_version TEXT,
  prompt_version TEXT,
  raw_text_hash TEXT,
  canonical_event_id TEXT,
  slug TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'published',
  indexable INTEGER NOT NULL DEFAULT 1,
  correction_version INTEGER NOT NULL DEFAULT 1,
  FOREIGN KEY (company_id) REFERENCES companies(id)
);

CREATE INDEX IF NOT EXISTS idx_events_company_time ON events(company_id, source_published_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_type_time ON events(event_type, source_published_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_impact_time ON events(impact_score DESC, source_published_at DESC);

CREATE TABLE IF NOT EXISTS event_metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL,
  metric_key TEXT NOT NULL,
  numeric_value REAL,
  text_value TEXT,
  unit TEXT,
  currency TEXT,
  source_fragment TEXT,
  FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
  UNIQUE(event_id, metric_key, numeric_value, text_value)
);

CREATE INDEX IF NOT EXISTS idx_event_metrics_event ON event_metrics(event_id);

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  display_name TEXT,
  email_verified_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS watchlists (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  name TEXT NOT NULL DEFAULT 'Default Watchlist',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_watchlists_user ON watchlists(user_id);

CREATE TABLE IF NOT EXISTS watchlist_items (
  watchlist_id TEXT NOT NULL,
  company_id INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (watchlist_id, company_id),
  FOREIGN KEY (watchlist_id) REFERENCES watchlists(id) ON DELETE CASCADE,
  FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS alert_preferences (
  user_id TEXT PRIMARY KEY,
  delivery_mode TEXT NOT NULL DEFAULT 'daily' CHECK (delivery_mode IN ('off','daily','immediate')),
  minimum_impact INTEGER NOT NULL DEFAULT 50,
  categories_json TEXT NOT NULL DEFAULT '[]',
  timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS entitlements (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  plan_code TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  starts_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  source_payment_id TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_entitlements_user_status ON entitlements(user_id, status, expires_at);

CREATE TABLE IF NOT EXISTS payments (
  order_id TEXT PRIMARY KEY,
  payment_id TEXT UNIQUE,
  user_id TEXT,
  plan_code TEXT NOT NULL,
  amount_paise INTEGER NOT NULL,
  currency TEXT NOT NULL DEFAULT 'INR',
  status TEXT NOT NULL DEFAULT 'created',
  webhook_event_id TEXT UNIQUE,
  raw_webhook_hash TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS job_runs (
  id TEXT PRIMARY KEY,
  job_name TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  rows_fetched INTEGER NOT NULL DEFAULT 0,
  rows_published INTEGER NOT NULL DEFAULT 0,
  source_mode TEXT,
  error_message TEXT,
  metadata_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_job_runs_name_started ON job_runs(job_name, started_at DESC);

CREATE TABLE IF NOT EXISTS corrections (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  reason TEXT NOT NULL,
  previous_json TEXT,
  corrected_json TEXT NOT NULL,
  corrected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
  UNIQUE(event_id, version)
);
