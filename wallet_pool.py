"""Wallet Pool System — Multi-address pool + robust scanner + price feed."""

import json, os, time, logging, threading, hashlib, base58, random, io
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple

import requests
import storage as s

logger = logging.getLogger(__name__)

# --- Constants ---
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
POOL_FILE = os.path.join(_pkg_dir, '.wallet_pool.json')
MIN_POOL_SIZE = 3
TARGET_POOL_SIZE = 5
MAX_RETRIES = 3

BSC_RPC_ENDPOINTS = [
    'https://bsc-dataseed1.binance.org/',
    'https://bsc-dataseed2.binance.org/',
    'https://bsc-dataseed3.binance.org/',
    'https://bsc-dataseed4.binance.org/',
    'https://bsc-dataseed1.defibit.io/',
    'https://bsc-dataseed2.defibit.io/',
]
_custom_bsc_rpc = os.environ.get('BSC_RPC_URL', '')
if _custom_bsc_rpc and _custom_bsc_rpc not in BSC_RPC_ENDPOINTS:
    BSC_RPC_ENDPOINTS.insert(0, _custom_bsc_rpc)

USDT_CONTRACT_ADDRESS = os.environ.get('USDT_CONTRACT_ADDRESS', '0x55d398326f99059fF775485246999027B3197955')
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
PAYMENT_TOLERANCE = float(os.environ.get('PAYMENT_TOLERANCE', '0.005'))

BLOCKCYPHER_ENDPOINTS = {
    'btc': 'https://api.blockcypher.com/v1/btc/main',
    'ltc': 'https://api.blockcypher.com/v1/ltc/main',
    'doge': 'https://api.blockcypher.com/v1/doge/main',
}

CHAIN_CONFIG = {
    'bsc': {'decimals': 1e18, 'confirms': 3, 'scan_interval': 60},
    'ton': {'decimals': 1e9, 'confirms': 3, 'scan_interval': 60},
    'ltc': {'decimals': 1e8, 'confirms': 2, 'scan_interval': 120},
    'doge': {'decimals': 1e8, 'confirms': 2, 'scan_interval': 120},
    'btc': {'decimals': 1e8, 'confirms': 2, 'scan_interval': 120},
    'tron': {'decimals': 1e6, 'confirms': 3, 'scan_interval': 60},
}

ALL_CHAINS = ['bsc', 'ton', 'ltc', 'doge', 'btc', 'tron']

# ===========================================================================
# PRICE FEED — Multi-source with fallback
# ===========================================================================

class PriceFeed:
    _cache: Dict[str, dict] = {}
    _CACHE_TTL = 300
    _lock = threading.Lock()

    @classmethod
    def get(cls, symbol: str) -> float:
        key = symbol.lower()
        if key == 'usdt':
            return 1.0
        now = time.time()
        cached = cls._cache.get(key)
        if cached and (now - cached['ts']) < cls._CACHE_TTL:
            return cached['price']
        price = cls._fetch(key)
        with cls._lock:
            if price and price > 0:
                cls._cache[key] = {'price': price, 'ts': now}
                return price
            if cached:
                return cached['price']
        return 0.0

    @classmethod
    def _fetch(cls, symbol: str) -> Optional[float]:
        for name, fn in [('coingecko', cls._coingecko), ('binance', cls._binance)]:
            try:
                p = fn(symbol)
                if p and p > 0:
                    return p
            except Exception as e:
                logger.debug('PriceFeed %s failed for %s: %s', name, symbol, e)
        return None

    @staticmethod
    def _coingecko(symbol: str) -> Optional[float]:
        ids = {'bnb': 'binancecoin', 'ton': 'the-open-network', 'ltc': 'litecoin',
               'doge': 'dogecoin', 'btc': 'bitcoin'}
        cid = ids.get(symbol)
        if not cid:
            return None
        r = requests.get('https://api.coingecko.com/api/v3/simple/price',
                         params={'ids': cid, 'vs_currencies': 'usd'}, timeout=10)
        return r.json().get(cid, {}).get('usd')

    @staticmethod
    def _binance(symbol: str) -> Optional[float]:
        r = requests.get('https://api.binance.com/api/v3/ticker/price',
                         params={'symbol': f'{symbol.upper()}USDT'}, timeout=10)
        r.raise_for_status()
        return float(r.json()['price'])

    @classmethod
    def get_all(cls) -> Dict[str, float]:
        prices = {}
        for sym in ['bnb', 'ton', 'ltc', 'doge', 'btc']:
            prices[sym] = cls.get(sym)
        return prices

# ===========================================================================
# WALLET POOL MANAGEMENT
# ===========================================================================

_pool_cache: Dict[str, list] = None
_pool_lock = threading.Lock()

def _load_pool() -> Dict[str, list]:
    global _pool_cache
    if _pool_cache is not None:
        if isinstance(_pool_cache, dict):
            return _pool_cache
        logger.warning('Pool cache is %s, expected dict, resetting', type(_pool_cache).__name__)
        _pool_cache = None
    try:
        if os.path.exists(POOL_FILE):
            with open(POOL_FILE, 'r') as f:
                raw = f.read()
                if raw.strip():
                    data = json.loads(raw)
                    if not isinstance(data, dict):
                        logger.warning('Pool file has invalid format, resetting')
                        raise ValueError('Invalid pool format')
                    _pool_cache = data
                else:
                    raise ValueError('Empty pool file')
        else:
            raise FileNotFoundError('Pool file not found')
    except Exception:
        _pool_cache = {}
        if not _restore_pool_from_settings():
            logger.info('Pool file not found and no backup available, will create fresh')
    return _pool_cache

def _save_pool():
    try:
        with open(POOL_FILE, 'w') as f:
            json.dump(_pool_cache, f, indent=2)
    except Exception as e:
        logger.error('Error saving wallet pool: %s', e)
    _backup_pool_to_settings()

def _backup_pool_to_settings():
    try:
        pool = _pool_cache if _pool_cache else _load_pool()
        existing = s.find_one('settings', key='wallet_pool_backup')
        if existing:
            s.update('settings', existing['id'], {'value': json.dumps(pool)})
        else:
            s.insert('settings', {'key': 'wallet_pool_backup', 'value': json.dumps(pool)})
    except Exception as e:
        logger.debug('Pool backup to settings failed: %s', e)

def _restore_pool_from_settings() -> bool:
    try:
        entry = s.find_one('settings', key='wallet_pool_backup')
        if entry and entry.get('value'):
            data = json.loads(entry['value'])
            if isinstance(data, dict) and data:
                global _pool_cache
                _pool_cache = data
                _save_pool()
                logger.info('Pool restored from settings backup (%d chains)', len(data))
                return True
    except Exception as e:
        logger.debug('Pool restore from settings failed: %s', e)
    return False

def get_pool_wallets(chain: str = None) -> dict:
    with _pool_lock:
        pool = _load_pool()
        if chain:
            return {chain: pool.get(chain, [])}
        return pool

def get_pool_addresses(chain: str = None) -> Dict[str, str]:
    pool = _load_pool()
    if chain:
        wallets = pool.get(chain, [])
        return {chain: [w['address'] for w in wallets]}
    result = {}
    for c, wallets in pool.items():
        result[c] = [w['address'] for w in wallets]
    return result

def count_pool_wallets(chain: str) -> int:
    pool = _load_pool()
    return len(pool.get(chain, []))

def _generate_wallet_for_chain(chain: str) -> Tuple[str, str]:
    if chain == 'bsc':
        return _gen_bsc()
    elif chain == 'ton':
        return _gen_ton()
    elif chain in ('ltc', 'doge', 'btc'):
        return _gen_ltc_doge(chain)
    elif chain == 'tron':
        return _gen_tron()
    raise ValueError(f'Unknown chain: {chain}')

def _gen_bsc() -> Tuple[str, str]:
    from eth_account import Account
    from eth_keyfile import create_keyfile_json
    acct = Account.create()
    ks = create_keyfile_json(acct.key, 'EAStoreTelegramPool@2024@', kdf='scrypt')
    return acct.address, json.dumps(ks)

def _gen_ton() -> Tuple[str, str]:
    from tonsdk.contract.wallet import Wallets, WalletVersionEnum
    mnemonics, pub_k, priv_k, wallet = Wallets.create(WalletVersionEnum.v4r2, workchain=0)
    addr = wallet.address.to_string(True, True, False)
    return addr, ' '.join(mnemonics)

def _gen_ltc_doge(chain: str) -> Tuple[str, str]:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    priv_bytes = os.urandom(32)
    priv = ec.derive_private_key(int.from_bytes(priv_bytes, 'big'), ec.SECP256K1())
    pub_uncomp = priv.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint)
    prefix = b'\x02' if pub_uncomp[-1] % 2 == 0 else b'\x03'
    pub_point = prefix + pub_uncomp[1:33]
    h = hashlib.sha256(pub_point).digest()
    ripe = hashlib.new('ripemd160', h).digest()
    addr_prefixes = {'ltc': b'\x30', 'doge': b'\x1e', 'btc': b'\x00'}
    versioned = addr_prefixes.get(chain, b'\x00') + ripe
    checksum = hashlib.sha256(hashlib.sha256(versioned).digest()).digest()[:4]
    address = base58.b58encode(versioned + checksum).decode()
    wif_versions = {'ltc': b'\xb0', 'doge': b'\x9e', 'btc': b'\x80'}
    wv = wif_versions.get(chain, b'\x80')
    wif_ver = wv + priv_bytes
    wif_cs = hashlib.sha256(hashlib.sha256(wif_ver).digest()).digest()[:4]
    wif = base58.b58encode(wif_ver + wif_cs).decode()
    return address, wif

def _gen_tron() -> Tuple[str, str]:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    from Crypto.Hash import keccak
    priv_bytes = os.urandom(32)
    priv = ec.derive_private_key(int.from_bytes(priv_bytes, 'big'), ec.SECP256K1())
    pub_uncomp = priv.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint)
    pub_key = pub_uncomp[1:]
    k = keccak.new(digest_bits=256)
    k.update(pub_key)
    addr_hash = k.digest()[-20:]
    versioned = b'\x41' + addr_hash
    checksum = hashlib.sha256(hashlib.sha256(versioned).digest()).digest()[:4]
    address = base58.b58encode(versioned + checksum).decode()
    return address, priv_bytes.hex()

def add_wallet_to_pool(chain: str, address: str, secret: str) -> bool:
    with _pool_lock:
        pool = _load_pool()
        if chain not in pool:
            pool[chain] = []
        for w in pool[chain]:
            if w['address'] == address:
                return False
        wallet = {
            'address': address,
            'secret': secret,
            'label': f'{chain}-{len(pool[chain]) + 1}',
            'assigned_tx_id': None,
            'created_at': datetime.utcnow().isoformat(),
            'last_balance': 0.0,
            'last_checked': None,
        }
        pool[chain].append(wallet)
        _save_pool()
        return True

def ensure_pool_size(chain: str, target: int = TARGET_POOL_SIZE):
    pool = _load_pool()
    current = len(pool.get(chain, []))
    if current >= target:
        return
    needed = target - current
    logger.info('Generating %d new wallet(s) for %s pool (current=%d, target=%d)',
                needed, chain, current, target)
    for i in range(needed):
        try:
            addr, secret = _generate_wallet_for_chain(chain)
            add_wallet_to_pool(chain, addr, secret)
            logger.info('Generated %s wallet #%d: %s', chain, current + i + 1, addr[:20])
        except Exception as e:
            logger.error('Failed to generate %s wallet: %s', chain, e)

def assign_wallet(chain: str, tx_id: int) -> Optional[str]:
    with _pool_lock:
        pool = _load_pool()
        wallets = pool.get(chain, [])
        for w in wallets:
            if not w.get('assigned_tx_id'):
                w['assigned_tx_id'] = tx_id
                _save_pool()
                _save_tx_assignment(tx_id, chain, w['address'])
                return w['address']
    return None

def _save_tx_assignment(tx_id: int, chain: str, address: str):
    try:
        key = f'wallet_tx_assign_{tx_id}'
        existing = s.find_one('settings', key=key)
        if existing:
            data = json.loads(existing['value']) if existing['value'] else {}
        else:
            data = {}
        data[chain] = address
        if existing:
            s.update('settings', existing['id'], {'value': json.dumps(data)})
        else:
            s.insert('settings', {'key': key, 'value': json.dumps(data)})
    except Exception as e:
        logger.debug('Failed to save tx assignment: %s', e)

def release_wallet(chain: str, address: str):
    with _pool_lock:
        pool = _load_pool()
        for w in pool.get(chain, []):
            if w['address'] == address:
                w['assigned_tx_id'] = None
                _save_pool()
                return True
    return False

def get_assigned_addresses(tx_id: int) -> Dict[str, str]:
    pool = _load_pool()
    result = {}
    for chain, wallets in pool.items():
        for w in wallets:
            if w.get('assigned_tx_id') == tx_id:
                result[chain] = w['address']
    if not result:
        result = _restore_tx_assignments(tx_id)
    return result

def _restore_tx_assignments(tx_id: int) -> Dict[str, str]:
    try:
        key = f'wallet_tx_assign_{tx_id}'
        entry = s.find_one('settings', key=key)
        if entry and entry.get('value'):
            return json.loads(entry['value'])
    except Exception as e:
        logger.debug('Failed to restore tx assignments: %s', e)
    return {}

def release_wallet_by_tx(tx_id: int):
    with _pool_lock:
        pool = _load_pool()
        released = False
        for chain, wallets in pool.items():
            for w in wallets:
                if w.get('assigned_tx_id') == tx_id:
                    w['assigned_tx_id'] = None
                    released = True
        if released:
            _save_pool()
    _clean_tx_assignment(tx_id)
    return released

def _clean_tx_assignment(tx_id: int):
    try:
        key = f'wallet_tx_assign_{tx_id}'
        existing = s.find_one('settings', key=key)
        if existing:
            s.update('settings', existing['id'], {'value': '{}'})
    except Exception:
        pass

def get_assigned_address(chain: str, tx_id: int) -> Optional[str]:
    pool = _load_pool()
    for w in pool.get(chain, []):
        if w.get('assigned_tx_id') == tx_id:
            return w['address']
    return None

def get_secret_for_address(chain: str, address: str) -> Optional[str]:
    pool = _load_pool()
    for w in pool.get(chain, []):
        if w['address'] == address:
            return w.get('secret')
    return None

# ===========================================================================
# CHAIN-SPECIFIC BALANCE CHECKERS
# ===========================================================================

def _retry(fn, *args, _label='', **kwargs):
    for attempt in range(MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                delay = [1, 3, 10][attempt]
                logger.debug('Retry %s attempt %d after %ds: %s', _label, attempt + 1, delay, e)
                time.sleep(delay)
            else:
                logger.warning('%s failed after %d attempts: %s', _label, MAX_RETRIES, e)
    return 0.0

# --- BSC ---

def _bsc_rpc_call(method, params, endpoints=None) -> Optional[dict]:
    eps = endpoints or BSC_RPC_ENDPOINTS
    for ep in eps:
        try:
            r = requests.post(ep, json={'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1}, timeout=10)
            data = r.json()
            if 'result' in data:
                return data
        except Exception:
            continue
    return None

def get_bsc_balance(address: str) -> Tuple[float, float]:
    bnb = _retry(_bsc_bnb_balance, address, _label='BSC-BNB')
    usdt = _retry(_bsc_usdt_balance, address, _label='BSC-USDT')
    return bnb, usdt

def _bsc_bnb_balance(address: str) -> float:
    data = _bsc_rpc_call('eth_getBalance', [address, 'latest'])
    if data and 'result' in data:
        return int(data['result'], 16) / 1e18
    return 0.0

def _bsc_usdt_balance(address: str) -> float:
    sig = '0x70a08231' + address[2:].lower().zfill(64)
    data = _bsc_rpc_call('eth_call', [{'to': USDT_CONTRACT_ADDRESS, 'data': sig}, 'latest'])
    if data and 'result' in data:
        return int(data['result'], 16) / 1e18
    return 0.0

# --- TON ---

TON_ENDPOINTS = ['https://toncenter.com/api/v2', 'https://toncenter.com/api/v2']

def get_ton_balance(address: str) -> float:
    return _retry(_ton_balance, address, _label='TON')

def _ton_balance(address: str) -> float:
    for ep in TON_ENDPOINTS:
        try:
            r = requests.get(f'{ep}/getAddressBalance', params={'address': address}, timeout=10)
            data = r.json()
            if data.get('ok') and 'result' in data:
                return int(data['result']) / 1e9
        except Exception:
            continue
    return 0.0

# --- BLOCKCYPHER CHAINS ---

def get_blockcypher_balance(chain: str, address: str) -> float:
    return _retry(_blockcypher_balance, chain, address, _label=f'{chain.upper()}')

def _blockcypher_balance(chain: str, address: str) -> float:
    ep = BLOCKCYPHER_ENDPOINTS.get(chain)
    if not ep:
        return 0.0
    r = requests.get(f'{ep}/addrs/{address}/balance', timeout=10)
    data = r.json()
    if 'balance' in data:
        return data['balance'] / 1e8
    return 0.0

# --- TRON ---

TRON_ENDPOINTS = ['https://api.trongrid.io', 'https://api.tronstack.io']

def get_tron_balance(address: str) -> float:
    return _retry(_tron_usdt_balance, address, _label='TRON')

def _tron_to_hex(b58_addr: str) -> Optional[str]:
    try:
        decoded = base58.b58decode(b58_addr)
        if len(decoded) >= 21:
            return '41' + decoded[1:21].hex()
    except Exception:
        return None

def _tron_usdt_balance(address: str) -> float:
    usdt = 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t'
    hex_addr = _tron_to_hex(address)
    if not hex_addr:
        return 0.0
    for ep in TRON_ENDPOINTS:
        try:
            r = requests.post(f'{ep}/wallet/triggerconstantcontract', json={
                'contract_address': _tron_to_hex(usdt),
                'function_selector': 'balanceOf(address)',
                'parameter': hex_addr[2:].zfill(64),
                'owner_address': hex_addr,
            }, timeout=10)
            rj = r.json()
            if rj.get('result', {}).get('result') and rj.get('constant_result'):
                return int(rj['constant_result'][0], 16) / 1e6
        except Exception:
            continue
    return 0.0

# --- Generic balance getter ---

def get_balance(chain: str, address: str) -> float:
    try:
        if chain == 'bsc':
            bnb, usdt = get_bsc_balance(address)
            return usdt + (bnb * PriceFeed.get('BNB'))
        elif chain == 'ton':
            return get_ton_balance(address) * PriceFeed.get('TON')
        elif chain in ('ltc', 'doge', 'btc'):
            return get_blockcypher_balance(chain, address) * PriceFeed.get(chain.upper())
        elif chain == 'tron':
            return get_tron_balance(address)
    except Exception as e:
        logger.error('get_balance %s %s: %s', chain, address[:16], e)
    return 0.0

# ===========================================================================
# PAYMENT DETECTION — Notifications via Telegram
# ===========================================================================

def _send_telegram_message(chat_id, text, parse_mode='Markdown'):
    if not BOT_TOKEN:
        return
    try:
        requests.post(f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage', json={
            'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode,
        }, timeout=10)
    except Exception as e:
        logger.error('Telegram notify error: %s', e)

def _get_wallet_log_group_id():
    entry = s.find_one('settings', key='wallet_log_group_id')
    if entry and entry.get('value'):
        try:
            return int(entry['value'])
        except (ValueError, TypeError):
            pass
    gid = os.environ.get('WALLET_LOG_GROUP_ID', '')
    if gid:
        return int(gid)
    return None

def _notify_payment_detected(user, amount_usdt, chain, tx_ref=None):
    group_id = _get_wallet_log_group_id()
    if not group_id:
        return
    label = user.get('first_name') or user.get('username') or f"User #{user['id']}"
    text = (
        f'\U0001f4b0 *Dep\xf3sito detectado --- {chain}*\n'
        f'\U0001f464 *Usuario:* `{label}`\n'
        f'\U0001f194 *ID:* `{user["id"]}`\n'
        f'\U0001f4b5 *Valor:* `{amount_usdt:.6f} USDT`\n'
        + (f'\U0001f517 *Tx:* `{tx_ref}`\n' if tx_ref else '')
        + '\U0001f4e5 *Acreditado a balance*'
    )
    _send_telegram_message(group_id, text)

def _notify_alert(msg: str):
    group_id = _get_wallet_log_group_id()
    if not group_id:
        return
    _send_telegram_message(group_id, f'\u26a0\ufe0f *Alerta:* {msg}')

# ===========================================================================
# PAYMENT PROCESSING — Confirm transactions, send EA, activate licenses
# ===========================================================================

MINI_APP_URL = os.environ.get('MINI_APP_URL', 'https://ea-store-telegram.onrender.com')


def _send_ea_to_user(user, transaction):
    """Send EA file to user via Telegram after payment confirmation."""
    try:
        product = s.get('products', transaction.get('product_id'))
        if not product:
            logger.error('send_ea_to_user: product not found for tx %s', transaction.get('id'))
            return
        try:
            import telebot
            bot = telebot.TeleBot(BOT_TOKEN, parse_mode='Markdown')
        except Exception as e:
            logger.error('send_ea_to_user: failed to create bot: %s', e)
            return
        from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

        telegram_id = user.get('telegram_id')
        if not telegram_id:
            logger.error('send_ea_to_user: user %s has no telegram_id', user.get('id'))
            return

        plan = s.get('plans', transaction.get('plan_id'))
        plan_label = plan['label'] if plan else 'Sin plan'
        lic = s.get('licenses', transaction.get('license_id'))
        license_key = (lic['license_key'] if lic else '').strip()
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton('\U0001f6d2 Abrir Tienda', web_app=WebAppInfo(url=MINI_APP_URL)))

        if license_key:
            caption = (
                f'\u2705 *{product["name"]}* \u2014 {plan_label}\n\n'
                f'*Tu licencia:*\n`{license_key}`\n\n'
                f'*Estado:* Activa'
            )
        else:
            caption = (f'\u2705 *{product["name"]}* \u2014 {plan_label}\n\n*Estado:* Activa')

        sent = False
        local_path = product.get('local_file_path')
        if local_path and os.path.exists(local_path):
            try:
                with open(local_path, 'rb') as f:
                    buf = io.BytesIO(f.read())
                buf.name = product.get('file_name') or product['name'] + (os.path.splitext(local_path)[1] or '.ex4')
                bot.send_document(telegram_id, buf,
                    caption=caption + '\n\n\U0001f4e5 Te adjuntamos el archivo del EA.',
                    reply_markup=keyboard, parse_mode='Markdown')
                sent = True
                logger.info('EA enviado desde archivo local a user %s (product %s)', user['id'], product['id'])
            except Exception as e:
                logger.warning('local file send failed for %s: %s', product['name'], e)

        if not sent:
            file_id = product.get('file_id') or product.get('file_url')
            if file_id:
                try:
                    bot.send_document(telegram_id, file_id,
                        caption=caption + '\n\n\U0001f4e5 Te adjuntamos el archivo del EA.',
                        reply_markup=keyboard, parse_mode='Markdown')
                    sent = True
                    logger.info('EA enviado por file_id a user %s (product %s)', user['id'], product['id'])
                except Exception as e:
                    logger.warning('file_id send failed for %s: %s', product['name'], e)

        if not sent:
            text = caption + '\n\n\U0001f4e5 El archivo del EA no est\u00e1 disponible. Contact\u00e1 al administrador.'
            try:
                bot.send_message(telegram_id, text, reply_markup=keyboard, parse_mode='Markdown')
            except Exception as e:
                logger.error('send_ea_to_user: fallback failed for user %s: %s', user['id'], e)
                try:
                    bot.send_message(telegram_id, text.replace('*', '').replace('_', ' '), reply_markup=keyboard)
                except Exception as e2:
                    logger.error('send_ea_to_user: plain text fallback failed for user %s: %s', user['id'], e2)

        logger.info('send_ea_to_user END: user=%s tx=%s sent=%s', user.get('id'), transaction.get('id'), sent)
    except Exception as e:
        logger.error('send_ea_to_user EXCEPTION for user %s: %s', user.get('id'), e, exc_info=True)


def _confirm_transaction(user, pending, balance_used=False):
    new_balance = (user.get('balance_usdt', 0) or 0)
    if not balance_used:
        new_balance -= pending['amount_usdt']
    s.update('users', user['id'], {'balance_usdt': new_balance})
    user['balance_usdt'] = new_balance

    s.update('transactions', pending['id'], {
        'status': 'confirmed',
        'confirmed_at': datetime.utcnow().isoformat(),
    })

    lic = s.get('licenses', pending.get('license_id'))
    if lic:
        plan = s.get('plans', pending.get('plan_id'))
        if plan:
            expires_at = datetime.utcnow() + timedelta(days=plan['duration_days'])
            s.update('licenses', lic['id'], {
                'expires_at': expires_at.isoformat(),
                'status': 'active',
            })

    if user.get('referred_by') and pending.get('amount_usdt', 0) > 0:
        ref = s.get('users', user['referred_by'])
        if ref:
            commission = pending['amount_usdt'] * 0.2
            ref_balance = (ref.get('balance_usdt', 0) or 0) + commission
            s.update('users', ref['id'], {'balance_usdt': ref_balance})
            s.insert('referral_earnings', {
                'referrer_id': ref['id'],
                'referred_id': user['id'],
                'amount_usdt': commission,
                'paid': False,
            })
            logger.info('Commission %.2f USDT to referrer #%s', commission, ref['id'])

    threading.Thread(target=_send_ea_to_user, args=(user, pending), daemon=True).start()
    _notify_payment_detected(user, pending['amount_usdt'], 'Balance' if balance_used else 'Wallet')

def _get_pending_for_address(chain: str, address: str) -> list:
    pending = s.find('transactions', status='pending')
    result = []
    for tx in pending:
        tx_id = tx['id']
        assigned = get_assigned_addresses(tx_id)
        if not assigned:
            assigned = _restore_tx_assignments(tx_id)
        if assigned.get(chain) == address:
            result.append(tx)
    return result

# ===========================================================================
# SCANNER
# ===========================================================================

def _process_wallet(chain: str, wallet: dict) -> dict:
    address = wallet['address']
    result = {'scanned': 0, 'credited': 0, 'confirmed': 0, 'errors': 0}
    current_usdt = get_balance(chain, address)

    if current_usdt == 0 and wallet.get('last_balance', 0) == 0:
        wallet['last_checked'] = datetime.utcnow().isoformat()
        return result

    result['scanned'] = 1
    diff = current_usdt - wallet.get('last_balance', 0)

    if diff > PAYMENT_TOLERANCE:
        pending_txs = _get_pending_for_address(chain, address)
        if not pending_txs:
            pending_txs = s.find('transactions', status='pending')

        best_match = None
        best_diff = float('inf')
        for tx in pending_txs:
            tx_amount = tx.get('amount_usdt', 0)
            if abs(tx_amount - diff) < 0.001:
                best_match = tx
                best_diff = 0
                break
            elif abs(tx_amount - diff) < best_diff:
                best_match = tx
                best_diff = abs(tx_amount - diff)

        if best_match and best_diff < 0.01:
            user = s.get('users', best_match['user_id'])
            if user:
                _confirm_transaction(user, best_match)
                release_wallet_by_tx(best_match['id'])
                result['credited'] += 1
                result['confirmed'] += 1
                logger.info('Payment matched: user=%s chain=%s amount=%.4f tx=%s',
                           user['id'], chain, diff, best_match['id'])
        else:
            if diff >= 1.0:
                _notify_alert(f'Unmatched deposit: {diff:.4f} USDT on {chain} {address[:16]}')

    wallet['last_balance'] = current_usdt
    wallet['last_checked'] = datetime.utcnow().isoformat()
    return result

def scan_all_wallets() -> dict:
    results = {'scanned': 0, 'credited': 0, 'confirmed': 0, 'errors': 0}
    pool = get_pool_wallets()

    for chain, wallets in pool.items():
        if not wallets:
            continue
        try:
            ensure_pool_size(chain, TARGET_POOL_SIZE)
        except Exception as e:
            logger.warning('Pool maintenance error for %s: %s', chain, e)

        for wallet in wallets:
            try:
                wr = _process_wallet(chain, wallet)
                for k in results:
                    results[k] += wr.get(k, 0)
            except Exception as e:
                logger.error('Error scanning %s wallet %s: %s', chain, wallet['address'][:16], e)
                results['errors'] += 1

    _save_pool()

    if results.get('confirmed'):
        logger.info('Scan completed: %s', results)

    return results

# ===========================================================================
# BACKGROUND SCANNER THREAD
# ===========================================================================

_scanner_running = False
_scanner_thread = None

def _background_scanner_loop():
    global _scanner_running
    _scanner_running = True
    time.sleep(15)
    logger.info('Background wallet pool scanner started')

    scan_count = 0
    while _scanner_running:
        try:
            results = scan_all_wallets()
            if results.get('confirmed'):
                logger.info('Scanner cycle %d: %s', scan_count, results)
        except Exception as e:
            logger.error('Scanner cycle error: %s', e, exc_info=True)

        scan_count += 1
        for _ in range(60):
            if not _scanner_running:
                break
            time.sleep(1)

    logger.info('Background scanner stopped')

def start_background_scanner():
    global _scanner_thread
    if _scanner_thread and _scanner_thread.is_alive():
        logger.warning('Scanner already running')
        return
    _scanner_thread = threading.Thread(target=_background_scanner_loop, daemon=True)
    _scanner_thread.start()
    logger.info('Background scanner thread started')

def stop_background_scanner():
    global _scanner_running
    _scanner_running = False
    logger.info('Stopping background scanner...')

# ===========================================================================
# INITIALIZATION
# ===========================================================================

def initialize_pool():
    chains = ['bsc', 'ton', 'ltc', 'doge', 'btc', 'tron']
    for chain in chains:
        try:
            count = count_pool_wallets(chain)
            if count < MIN_POOL_SIZE:
                logger.info('Pool %s has %d wallets, generating up to %d', chain, count, TARGET_POOL_SIZE)
                ensure_pool_size(chain, TARGET_POOL_SIZE)
        except Exception as e:
            logger.warning('Pool init error for %s: %s', chain, e)
    logger.info('Wallet pool initialized')