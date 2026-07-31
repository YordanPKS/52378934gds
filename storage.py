import sqlite3, json, os, threading, time
from flask import request
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ea_store.db')

_local = threading.local()


def _get_conn():
    if not getattr(_local, 'conn', None):
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute('PRAGMA journal_mode=WAL')
        _local.conn.execute('PRAGMA busy_timeout=5000')
    return _local.conn


def _serialize(val):
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    return val


def _deserialize(val):
    if val is None:
        return None
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val


# ─── Schema ────────────────────────────────────────────────

SCHEMA = {
    'users': '''
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id TEXT UNIQUE NOT NULL,
        username TEXT,
        first_name TEXT,
        referral_code TEXT,
        referred_by INTEGER,
        balance_usdt REAL DEFAULT 0,
        is_admin INTEGER DEFAULT 0,
        is_banned INTEGER DEFAULT 0,
        bsc_wallet_address TEXT,
        bsc_wallet_mnemonic TEXT,
        bsc_wallet_keystore TEXT,
        ton_wallet_address TEXT,
        ton_wallet_mnemonic TEXT,
        ltc_wallet_address TEXT,
        ltc_wallet_keystore TEXT,
        doge_wallet_address TEXT,
        doge_wallet_keystore TEXT,
        btc_wallet_address TEXT,
        btc_wallet_keystore TEXT,
        tron_wallet_address TEXT,
        tron_wallet_keystore TEXT,
        lifetime INTEGER DEFAULT 0,
        lifetime_products TEXT,
        platform TEXT DEFAULT 'MT4,MT5',
        created_at TEXT DEFAULT (datetime('now'))
    ''',
    'products': '''
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        platform TEXT DEFAULT 'MT4,MT5',
        file_id TEXT,
        file_name TEXT,
        file_url TEXT,
        local_file_path TEXT,
        image_url TEXT,
        is_active INTEGER DEFAULT 1,
        plans TEXT DEFAULT '[]',
        ea_id TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    ''',
    'plans': '''
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        label TEXT NOT NULL,
        duration_days INTEGER NOT NULL,
        price_usdt REAL NOT NULL DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
    ''',
    'licenses': '''
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        plan_id INTEGER,
        plan_label TEXT,
        plan_duration_days INTEGER,
        license_key TEXT UNIQUE NOT NULL,
        transaction_id INTEGER,
        status TEXT DEFAULT 'active',
        activated_accounts TEXT DEFAULT '[]',
        assigned_account TEXT,
        expires_at TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE SET NULL
    ''',
    'transactions': '''
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        product_id INTEGER,
        plan_id INTEGER,
        license_id INTEGER,
        product_name TEXT,
        plan_label TEXT,
        amount_usdt REAL,
        currency TEXT DEFAULT 'USDT',
        tx_hash TEXT,
        status TEXT DEFAULT 'pending',
        license_key TEXT,
        confirmed_at TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ''',
    'settings': '''
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE NOT NULL,
        value TEXT
    ''',
    'referral_earnings': '''
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id INTEGER NOT NULL,
        referred_id INTEGER,
        amount_usdt REAL,
        source TEXT,
        paid INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (referrer_id) REFERENCES users(id) ON DELETE CASCADE
    ''',
    'withdrawal_requests': '''
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount_usdt REAL,
        wallet_address TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ''',
    'tickets': '''
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        subject TEXT,
        message TEXT,
        replies TEXT DEFAULT '[]',
        status TEXT DEFAULT 'open',
        updated_at TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ''',
    'shared_wallets': '''
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chain TEXT UNIQUE NOT NULL,
        address TEXT NOT NULL,
        secret TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    ''',
    'bot_states': '''
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT NOT NULL,
        state_type TEXT NOT NULL,
        state_data TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    ''',
    'wallet_keystores': '''
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        label TEXT NOT NULL,
        address TEXT NOT NULL,
        keystore_json TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    ''',
    'license_validations': '''
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        license_key TEXT,
        license_id INTEGER,
        product_id INTEGER,
        ea_id TEXT,
        mt4_account TEXT,
        ip TEXT,
        result TEXT,
        detail TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    ''',
}


def init_db():
    conn = _get_conn()
    for table, schema in SCHEMA.items():
        conn.execute(f'CREATE TABLE IF NOT EXISTS {table} ({schema})')
    conn.commit()
    _migrate(conn)


def _migrate(conn):
    migrations = {
        'transactions': ['plan_id INTEGER', 'license_id INTEGER'],
        'products': ['ea_id TEXT'],
        'tickets': ['message TEXT', "replies TEXT DEFAULT '[]'", 'updated_at TEXT'],
        'licenses': ['plan_id INTEGER'],
        'users': ['lifetime INTEGER DEFAULT 0', "lifetime_products TEXT"],
    }
    for table, cols in migrations.items():
        for col_def in cols:
            try:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN {col_def}')
            except Exception:
                pass
    conn.commit()


# ─── Generic CRUD ──────────────────────────────────────────

def insert(table, data):
    data = dict(data)
    cols = ', '.join(data.keys())
    vals = ', '.join('?' for _ in data)
    serialized = [_serialize(v) for v in data.values()]
    conn = _get_conn()
    cur = conn.execute(f'INSERT INTO {table} ({cols}) VALUES ({vals})', serialized)
    conn.commit()
    data['id'] = cur.lastrowid
    return data


def update(table, id, data):
    if not data:
        return get(table, id)
    sets = ', '.join(f'{k}=?' for k in data)
    serialized = [_serialize(v) for v in data.values()] + [id]
    conn = _get_conn()
    conn.execute(f'UPDATE {table} SET {sets} WHERE id=?', serialized)
    conn.commit()
    return get(table, id)


def delete(table, id):
    conn = _get_conn()
    conn.execute(f'DELETE FROM {table} WHERE id=?', (id,))
    conn.commit()


def get(table, id):
    conn = _get_conn()
    cur = conn.execute(f'SELECT * FROM {table} WHERE id=?', (id,))
    row = cur.fetchone()
    return _row_to_dict(row) if row else None


def find_one(table, **kwargs):
    conn = _get_conn()
    where = ' AND '.join(f'{k}=?' for k in kwargs)
    cur = conn.execute(f'SELECT * FROM {table} WHERE {where} LIMIT 1', tuple(kwargs.values()))
    row = cur.fetchone()
    return _row_to_dict(row) if row else None


def find(table, **kwargs):
    conn = _get_conn()
    order_field = kwargs.pop('_order_by', None)
    order_desc = kwargs.pop('_order_desc', True)
    sql = f'SELECT * FROM {table}'
    params = []
    if kwargs:
        where = ' AND '.join(f'{k}=?' for k in kwargs)
        sql += f' WHERE {where}'
        params = list(kwargs.values())
    if order_field:
        order = 'DESC' if order_desc else 'ASC'
        sql += f' ORDER BY {order_field} {order}'
    cur = conn.execute(sql, params)
    return [_row_to_dict(r) for r in cur.fetchall()]


def all(table, order_by=None, desc=True):
    conn = _get_conn()
    sql = f'SELECT * FROM {table}'
    if order_by:
        order = 'DESC' if desc else 'ASC'
        sql += f' ORDER BY {order_by} {order}'
    cur = conn.execute(sql)
    return [_row_to_dict(r) for r in cur.fetchall()]


def order_by(table, field, desc=True):
    conn = _get_conn()
    order = 'DESC' if desc else 'ASC'
    cur = conn.execute(f'SELECT * FROM {table} ORDER BY {field} {order}')
    return [_row_to_dict(r) for r in cur.fetchall()]


def filter_order_by(table, field, desc=True, **kwargs):
    conn = _get_conn()
    where = ' AND '.join(f'{k}=?' for k in kwargs)
    order = 'DESC' if desc else 'ASC'
    cur = conn.execute(f'SELECT * FROM {table} WHERE {where} ORDER BY {field} {order}', tuple(kwargs.values()))
    return [_row_to_dict(r) for r in cur.fetchall()]


def count(table, **kwargs):
    conn = _get_conn()
    if not kwargs:
        cur = conn.execute(f'SELECT COUNT(*) FROM {table}')
    else:
        where = ' AND '.join(f'{k}=?' for k in kwargs)
        cur = conn.execute(f'SELECT COUNT(*) FROM {table} WHERE {where}', tuple(kwargs.values()))
    return cur.fetchone()[0]


def sum_field(table, field, **kwargs):
    conn = _get_conn()
    if not kwargs:
        cur = conn.execute(f'SELECT COALESCE(SUM({field}), 0) FROM {table}')
    else:
        where = ' AND '.join(f'{k}=?' for k in kwargs)
        cur = conn.execute(f'SELECT COALESCE(SUM({field}), 0) FROM {table} WHERE {where}', tuple(kwargs.values()))
    return cur.fetchone()[0]


def _row_to_dict(row):
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, str) and v.startswith(('[', '{')):
            d[k] = _deserialize(v)
    return d


def json_body():
    """Obtiene JSON del body ignorando Content-Type (proxy-friendly)."""
    return request.get_json(force=True, silent=True)
