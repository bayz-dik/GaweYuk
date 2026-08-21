CREATE TABLE IF NOT EXISTS career_legacy_imports (
    user_id TEXT PRIMARY KEY,
    twin_id TEXT NOT NULL UNIQUE,
    input_fingerprint TEXT NOT NULL,
    imported_at TEXT NOT NULL,

    FOREIGN KEY(twin_id)
        REFERENCES career_twins(twin_id)
);

CREATE INDEX IF NOT EXISTS idx_career_legacy_imports_twin
ON career_legacy_imports(twin_id);
