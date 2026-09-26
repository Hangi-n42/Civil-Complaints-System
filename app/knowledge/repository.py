"""One SQLite ledger, JSON payloads and database-enforced identities."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class KnowledgeRepository:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY, namespace TEXT NOT NULL, external_id TEXT,
                    payload TEXT NOT NULL, UNIQUE(namespace, external_id));
                CREATE TABLE IF NOT EXISTS versions (
                    id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
                    sha256 TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(source_id, sha256));
                CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS blocks (
                    id TEXT PRIMARY KEY, version_id TEXT NOT NULL REFERENCES versions(id),
                    run_id TEXT NOT NULL REFERENCES runs(id), unit_id TEXT NOT NULL,
                    block_order INTEGER NOT NULL, payload TEXT NOT NULL,
                    UNIQUE(run_id, unit_id, block_order));
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def get(db, table, object_id):
        if table not in {'sources', 'versions', 'runs', 'blocks'}:
            raise ValueError('Unknown ledger table')
        row = db.execute(f'SELECT payload FROM {table} WHERE id=?', (object_id,)).fetchone()
        if row is None:
            raise KeyError(object_id)
        return json.loads(row['payload'])

    @staticmethod
    def save(db, table, value):
        if table not in {'versions', 'runs'}:
            raise ValueError('Unsupported update')
        db.execute(f'UPDATE {table} SET payload=? WHERE id=?',
                   (json.dumps(value, ensure_ascii=False), value['id']))
