"""Wallet Pool API routes for db-api."""
import json
from flask import Blueprint, request, jsonify
import wallet_pool as wp
import storage as s

bp = Blueprint('wallet_pool', __name__)

_KEYSTORE_PASS = 'EAStoreTelegramPool@2024@'

def _decrypt_bsc_key(keystore_json: str) -> str:
    """Decrypt a BSC keystore JSON and return the raw hex private key."""
    from eth_account import Account
    ks = json.loads(keystore_json)
    return Account.decrypt(ks, _KEYSTORE_PASS).hex()


@bp.route('/wallet_pool/export-key', methods=['POST'])
def export_key():
    """Get the raw private key for a wallet (for import into Trust Wallet / MetaMask)."""
    body = request.get_json(force=True)
    chain = body.get('chain', '').lower()
    address = body.get('address', '')
    if not chain or not address:
        return jsonify({'error': 'chain and address required'}), 400
    pool = wp.get_pool_wallets()
    wallets = pool.get(chain, [])
    for w in wallets:
        if w['address'] == address:
            secret = w.get('secret', '')
            if not secret:
                return jsonify({'error': 'wallet has no secret'}), 404
            if chain == 'bsc':
                try:
                    key = _decrypt_bsc_key(secret)
                except Exception as e:
                    return jsonify({'error': f'failed to decrypt: {e}'}), 500
                return jsonify({'chain': chain, 'address': address,
                                'private_key': f'0x{key}', 'format': 'hex'})
            elif chain == 'ton':
                return jsonify({'chain': chain, 'address': address,
                                'private_key': secret, 'format': 'mnemonic'})
            elif chain in ('ltc', 'doge', 'btc'):
                return jsonify({'chain': chain, 'address': address,
                                'private_key': secret, 'format': 'wif'})
            elif chain == 'tron':
                return jsonify({'chain': chain, 'address': address,
                                'private_key': f'0x{secret}', 'format': 'hex'})
            return jsonify({'chain': chain, 'address': address,
                            'private_key': secret, 'format': 'raw'})
    return jsonify({'error': 'address not found in pool'}), 404


@bp.route('/wallet_pool/assign', methods=['POST'])
def assign():
    """Assign a pool wallet for a chain to a transaction."""
    body = request.get_json(force=True)
    chain = body.get('chain', '').lower()
    tx_id = body.get('tx_id')
    if not chain or not tx_id:
        return jsonify({'error': 'chain and tx_id required'}), 400
    addr = wp.assign_wallet(chain, tx_id)
    if addr:
        return jsonify({'address': addr, 'chain': chain})
    return jsonify({'error': 'no available wallet'}), 404


@bp.route('/wallet_pool/addresses', methods=['GET'])
def get_addresses():
    """Get assigned addresses for a transaction."""
    tx_id = request.args.get('tx_id')
    if not tx_id:
        return jsonify({'error': 'tx_id required'}), 400
    addrs = wp.get_assigned_addresses(int(tx_id))
    return jsonify(addrs)


@bp.route('/wallet_pool/release-by-tx', methods=['POST'])
def release_by_tx():
    """Release wallets assigned to a transaction."""
    body = request.get_json(force=True)
    tx_id = body.get('tx_id')
    if not tx_id:
        return jsonify({'error': 'tx_id required'}), 400
    wp.release_wallet_by_tx(int(tx_id))
    return jsonify({'ok': True})


@bp.route('/wallet_pool/release', methods=['POST'])
def release():
    """Release a specific wallet."""
    body = request.get_json(force=True)
    chain = body.get('chain', '').lower()
    address = body.get('address')
    if not chain or not address:
        return jsonify({'error': 'chain and address required'}), 400
    wp.release_wallet(chain, address)
    return jsonify({'ok': True})


@bp.route('/wallet_pool/status', methods=['GET'])
def pool_status():
    """Get pool status (wallets per chain)."""
    pool = wp.get_pool_wallets()
    result = {}
    for chain, wallets in pool.items():
        result[chain] = {
            'total': len(wallets),
            'available': sum(1 for w in wallets if not w.get('assigned_tx_id')),
            'in_use': sum(1 for w in wallets if w.get('assigned_tx_id')),
        }
    return jsonify(result)


@bp.route('/wallet_pool/wallets', methods=['GET'])
def list_wallets():
    """Get all wallets with details."""
    chain = request.args.get('chain', '').lower() or None
    pool = wp.get_pool_wallets(chain)
    result = []
    for c, wallets in pool.items():
        for w in wallets:
            result.append({
                'chain': c,
                'address': w['address'],
                'label': w.get('label', ''),
                'in_use': bool(w.get('assigned_tx_id')),
                'assigned_tx_id': w.get('assigned_tx_id'),
                'last_balance': w.get('last_balance', 0),
                'last_checked': w.get('last_checked'),
            })
    return jsonify(result)


@bp.route('/wallet_pool/balance', methods=['GET'])
def check_balance():
    """Get balance for a wallet on a chain."""
    chain = request.args.get('chain', '').lower()
    address = request.args.get('address', '')
    if not chain or not address:
        return jsonify({'error': 'chain and address required'}), 400
    balance = wp.get_balance(chain, address)
    return jsonify({'chain': chain, 'address': address, 'balance_usdt': balance})


@bp.route('/wallet_pool/initialize', methods=['POST'])
def initialize():
    """Initialize pool (ensure min wallets per chain)."""
    wp.initialize_pool()
    return jsonify({'ok': True})


@bp.route('/wallet_pool/scan', methods=['POST'])
def trigger_scan():
    """Trigger an immediate scan of all wallets."""
    results = wp.scan_all_wallets()
    return jsonify(results)


@bp.route('/wallet_pool/crypto-amounts', methods=['GET'])
def crypto_amounts():
    """Get equivalent crypto amounts for a USDT price."""
    price_usdt = request.args.get('amount', type=float)
    if not price_usdt or price_usdt <= 0:
        return jsonify({'error': 'amount (USDT) required'}), 400
    prices = wp.PriceFeed.get_all()
    amounts = {
        'bsc': [
            {'token': 'BNB', 'amount': round(price_usdt / prices.get('bnb', 0), 6) if prices.get('bnb', 0) > 0 else None},
            {'token': 'USDT', 'amount': round(price_usdt, 2)},
        ],
        'tron': {'token': 'USDT', 'amount': round(price_usdt, 2)},
    }
    p = prices.get('ton', 0)
    amounts['ton'] = {'token': 'TON', 'amount': round(price_usdt / p, 4) if p > 0 else None}
    p = prices.get('ltc', 0)
    amounts['ltc'] = {'token': 'LTC', 'amount': round(price_usdt / p, 6) if p > 0 else None}
    p = prices.get('doge', 0)
    amounts['doge'] = {'token': 'DOGE', 'amount': round(price_usdt / p, 2) if p > 0 else None}
    p = prices.get('btc', 0)
    amounts['btc'] = {'token': 'BTC', 'amount': round(price_usdt / p, 8) if p > 0 else None}
    return jsonify({'prices': prices, 'amounts': amounts})