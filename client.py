"""HTTP client para que el bot se comunique con db_api."""

import os, json, logging, urllib.parse
import requests

logger = logging.getLogger(__name__)

DB_API_URL = os.getenv('DB_API_URL', 'http://127.0.0.1:5100')
PA_PROXY = os.getenv('PA_PROXY_URL', 'https://api.allorigins.win/raw?url=')

_HEADERS = {'Content-Type': 'application/json'}


def _proxy_url(path):
    full = f'{DB_API_URL}/api{path}'
    if PA_PROXY:
        sep = '' if PA_PROXY.endswith(('?', '&', '=')) else '/'
        return f'{PA_PROXY}{sep}{urllib.parse.quote(full, safe="")}'
    return full


def _req(method, path, body=None):
    url = _proxy_url(path)
    try:
        r = requests.request(method, url, json=body, headers=_HEADERS, timeout=10)
        if r.status_code >= 400:
            logger.warning('db_api %s %s -> %s: %s', method, path, r.status_code, r.text[:200])
            return None
        return r.json() if r.text else None
    except requests.RequestException as e:
        logger.warning('db_api %s %s -> %s', method, path, e)
        return None


def _list(result):
    return result if isinstance(result, list) else []


def _dict(result):
    return result if isinstance(result, dict) else {}


# ─── Lifetime ────────────────────────────────────────────

def set_lifetime(uid, enabled=True, products='all'):
    return _req('PUT', f'/users/{uid}/lifetime', {'enabled': enabled, 'products': products})


# ─── Users ─────────────────────────────────────────────────

def get_user(uid):
    return _req('GET', f'/users/{uid}')


def find_user(**kwargs):
    qs = '&'.join(f'{k}={v}' for k, v in kwargs.items())
    return _req('GET', f'/users/find?{qs}')


def find_one_user(**kwargs):
    results = find_user(**kwargs)
    if isinstance(results, list) and results:
        return results[0]
    return None


def by_telegram(tid):
    return _req('GET', f'/users/by-telegram/{tid}')


def create_user(data):
    return _req('POST', '/users', data)


def update_user(uid, data):
    return _req('PUT', f'/users/{uid}', data)


def delete_user(uid):
    return _req('DELETE', f'/users/{uid}')


def all_users():
    return _req('GET', '/users')


# ─── Products ──────────────────────────────────────────────

def get_product(pid):
    return _req('GET', f'/products/{pid}')


def all_products(active_only=False):
    path = '/products?active_only=1' if active_only else '/products'
    return _req('GET', path)


def create_product(data):
    return _req('POST', '/products', data)


def update_product(pid, data):
    return _req('PUT', f'/products/{pid}', data)


def delete_product(pid):
    return _req('DELETE', f'/products/{pid}')


# ─── Settings ──────────────────────────────────────────────

def get_setting(key):
    resp = _req('GET', f'/settings/{key}')
    if resp:
        return resp.get('value')
    return None


def set_setting(key, value):
    return _req('PUT', f'/settings/{key}', {'value': value})


def all_settings():
    return _req('GET', '/settings')


# ─── Shared Wallets ───────────────────────────────────────

def get_shared_wallet(wid):
    return _req('GET', f'/shared_wallets/{wid}')


def all_shared_wallets():
    return _req('GET', '/shared_wallets')


def create_shared_wallet(data):
    return _req('POST', '/shared_wallets', data)


def update_shared_wallet(wid, data):
    return _req('PUT', f'/shared_wallets/{wid}', data)


def delete_shared_wallet(wid):
    return _req('DELETE', f'/shared_wallets/{wid}')


def get_shared_wallet_by_chain(chain):
    resp = all_shared_wallets()
    if isinstance(resp, list):
        for w in resp:
            if w.get('chain') == chain:
                return w
    return None


# ─── File Upload / EA files ───────────────────────────

def upload_file(file_path, product_id=None):
    import base64
    with open(file_path, 'rb') as f:
        raw = f.read()
    payload = {'filename': os.path.basename(file_path), 'data': base64.b64encode(raw).decode()}
    if product_id:
        payload['product_id'] = product_id
    return _req('POST', '/files/upload', payload)


def upload_ea(file_path, product_id='tmp', name=None):
    import base64
    with open(file_path, 'rb') as f:
        raw = f.read()
    payload = {
        'filename': name or os.path.basename(file_path),
        'data': base64.b64encode(raw).decode(),
        'product_id': product_id,
    }
    return _req('POST', '/files/ea/upload', payload)


def download_ea(product_id, name):
    return _req('GET', f'/files/ea/download?product_id={product_id}&name={name}')


def list_ea_files(product_id=None):
    qs = f'?product_id={product_id}' if product_id else ''
    return _req('GET', f'/files/ea/list{qs}')


def delete_ea_file(product_id, name):
    return _req('DELETE', f'/files/ea/delete', {'product_id': product_id, 'name': name})


# ─── Admin (export / import) ──────────────────────────────

def export_db():
    return _req('GET', '/admin/export')


def import_db(data):
    return _req('POST', '/admin/import', data)


# ─── Wallet Keystores ─────────────────────────────────────

def all_wallet_keystores():
    return _req('GET', '/wallet_keystores')


def get_wallet_keystore(wid):
    return _req('GET', f'/wallet_keystores/{wid}')


def create_wallet_keystore(data):
    return _req('POST', '/wallet_keystores', data)


def delete_wallet_keystore(wid):
    return _req('DELETE', f'/wallet_keystores/{wid}')


# ─── Bot States ──────────────────────────────────────────

def get_bot_state(chat_id, state_type):
    resp = _req('GET', f'/bot_states?chat_id={chat_id}&state_type={state_type}')
    if isinstance(resp, list) and resp:
        return resp[0]
    return None


def set_bot_state(chat_id, state_type, state_data=None):
    return _req('POST', '/bot_states', {
        'chat_id': str(chat_id),
        'state_type': state_type,
        'state_data': json.dumps(state_data) if state_data is not None else None,
    })


def delete_bot_state(chat_id, state_type):
    return _req('POST', '/bot_states/delete', {
        'chat_id': str(chat_id),
        'state_type': state_type,
    })


# ─── Health ────────────────────────────────────────────────

def health():
    return _req('GET', '/health')
