CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL DEFAULT '#888888',
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    active INTEGER NOT NULL DEFAULT 1,
    outlook_category_name TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_categories_role ON categories(role_id);
CREATE INDEX IF NOT EXISTS idx_categories_outlook ON categories(outlook_category_name);

CREATE TABLE IF NOT EXISTS time_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    start_ts INTEGER NOT NULL,  -- unix seconds, UTC
    end_ts INTEGER,             -- NULL while active
    source TEXT NOT NULL,       -- enum: manual, auto_outlook, auto_meeting, manual_override, screen_lock_recovery, idle_recovery
    comment TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    modified_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_entries_start ON time_entries(start_ts);
CREATE INDEX IF NOT EXISTS idx_entries_end ON time_entries(end_ts);
CREATE INDEX IF NOT EXISTS idx_entries_category ON time_entries(category_id);

CREATE TABLE IF NOT EXISTS outlook_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time_entry_id INTEGER NOT NULL REFERENCES time_entries(id) ON DELETE CASCADE,
    outlook_item_id TEXT NOT NULL,
    subject TEXT,
    item_type TEXT NOT NULL  -- mail, task, appointment
);

CREATE TABLE IF NOT EXISTS rejected_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    outlook_category_name TEXT NOT NULL,
    app_category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    rejection_count INTEGER NOT NULL DEFAULT 0,
    silenced INTEGER NOT NULL DEFAULT 0,
    last_rejected_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(outlook_category_name, app_category_id)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
