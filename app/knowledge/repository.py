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
                CREATE TABLE IF NOT EXISTS ontology_versions (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS changesets (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS decisions (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY, namespace TEXT NOT NULL, official_id TEXT,
                    payload TEXT NOT NULL, UNIQUE(namespace, official_id));
                CREATE TABLE IF NOT EXISTS entity_links (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, unit_id TEXT NOT NULL,
                    local_candidate_key TEXT NOT NULL, payload TEXT NOT NULL,
                    UNIQUE(run_id, unit_id, local_candidate_key));
                CREATE TABLE IF NOT EXISTS assertions (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, unit_id TEXT NOT NULL,
                    local_candidate_key TEXT NOT NULL, payload TEXT NOT NULL,
                    UNIQUE(run_id, unit_id, local_candidate_key));
                CREATE TABLE IF NOT EXISTS evidence (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS knowledge_state (
                    id INTEGER PRIMARY KEY CHECK(id=1), active_snapshot_id TEXT REFERENCES snapshots(id),
                    status_revision INTEGER NOT NULL DEFAULT 0);
                INSERT OR IGNORE INTO knowledge_state(id) VALUES(1);
                CREATE TABLE IF NOT EXISTS availability_history (
                    id TEXT PRIMARY KEY, status_revision INTEGER NOT NULL,
                    target_type TEXT NOT NULL, target_id TEXT NOT NULL, payload TEXT NOT NULL,
                    UNIQUE(status_revision,target_type,target_id));
                CREATE TABLE IF NOT EXISTS snapshot_events (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
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
        if table not in {'sources', 'versions', 'runs', 'blocks', 'ontology_versions', 'changesets', 'decisions',
                         'entities', 'entity_links', 'assertions', 'evidence', 'snapshots'}:
            raise ValueError('Unknown ledger table')
        row = db.execute(f'SELECT payload FROM {table} WHERE id=?', (object_id,)).fetchone()
        if row is None:
            raise KeyError(object_id)
        return json.loads(row['payload'])

    @staticmethod
    def save(db, table, value):
        if table not in {'versions', 'runs', 'changesets', 'entity_links', 'assertions', 'entities'}:
            raise ValueError('Unsupported update')
        db.execute(f'UPDATE {table} SET payload=? WHERE id=?',
                   (json.dumps(value, ensure_ascii=False), value['id']))
