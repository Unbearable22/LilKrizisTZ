import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

def now():
    return datetime.now(timezone.utc).isoformat()

def dumps(value):
    return json.dumps(value, ensure_ascii=False)

class Database:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'assistant.sqlite3'
        with self.connect() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS municipalities(id TEXT PRIMARY KEY, name TEXT NOT NULL, boundary TEXT, source_url TEXT, verified_at TEXT);
            CREATE TABLE IF NOT EXISTS rules(id INTEGER PRIMARY KEY, municipality_id TEXT NOT NULL REFERENCES municipalities(id), zone TEXT NOT NULL, version TEXT NOT NULL, data TEXT NOT NULL, verified_by TEXT, verified_at TEXT, active INTEGER NOT NULL DEFAULT 1, UNIQUE(municipality_id,zone,version));
            CREATE TABLE IF NOT EXISTS cases(id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS analyses(id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES cases(id), data TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sources(id INTEGER PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL UNIQUE, municipality_id TEXT REFERENCES municipalities(id), kind TEXT NOT NULL, digest TEXT, last_checked TEXT, error TEXT);
            CREATE TABLE IF NOT EXISTS revisions(id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id), digest TEXT NOT NULL, previous_text TEXT, content TEXT NOT NULL, artifact TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(source_id,digest));
            CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, case_id INTEGER REFERENCES cases(id), revision_id INTEGER NOT NULL REFERENCES revisions(id), data TEXT NOT NULL, delivered_at TEXT, UNIQUE(owner_id,case_id,revision_id));
            CREATE TABLE IF NOT EXISTS nspd_reports(id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES cases(id), digest TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(case_id,digest));
            CREATE TABLE IF NOT EXISTS sessions(owner_id INTEGER PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS legal_documents(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, version TEXT NOT NULL, source_url TEXT NOT NULL, citation TEXT NOT NULL, content TEXT NOT NULL, valid_until TEXT NOT NULL, verified_by TEXT NOT NULL, verified_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, UNIQUE(kind,citation,version));
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL, entity TEXT NOT NULL, created_at TEXT NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=20)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def rows(self, sql, args=()):
        with self.connect() as c:
            return [dict(r) for r in c.execute(sql, args)]

    def execute(self, sql, args=()):
        with self.connect() as c:
            return c.execute(sql, args).lastrowid

    def audit(self, actor, action, entity):
        self.execute('INSERT INTO audit(actor,action,entity,created_at) VALUES(?,?,?,?)', (str(actor), action, str(entity), now()))

    def state(self, key, value=None):
        if value is not None:
            self.execute('INSERT INTO state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, str(value)))
            return value
        rows = self.rows('SELECT value FROM state WHERE key=?', (key,))
        return rows[0]['value'] if rows else None

    def session(self, owner, value=None):
        if value is not None:
            self.execute('INSERT INTO sessions VALUES(?,?) ON CONFLICT(owner_id) DO UPDATE SET data=excluded.data', (owner, dumps(value)))
            return value
        rows = self.rows('SELECT data FROM sessions WHERE owner_id=?', (owner,))
        return json.loads(rows[0]['data']) if rows else {}
