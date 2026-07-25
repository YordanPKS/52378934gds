import time, hashlib, base64
from flask import Blueprint, request, jsonify
import storage as s

bp = Blueprint('users', __name__)


@bp.route('/users', methods=['GET'])
def list_users():
    return jsonify(s.all('users'))


@bp.route('/users/<int:uid>', methods=['GET'])
def get_user(uid):
    u = s.get('users', uid)
    if not u:
        return jsonify({'error': 'not found'}), 404
    return jsonify(u)


@bp.route('/users', methods=['POST'])
def create_user():
    body = request.get_json(force=True)
    if not body.get('telegram_id'):
        return jsonify({'error': 'telegram_id required'}), 400
    existing = s.find_one('users', telegram_id=str(body['telegram_id']))
    if existing:
        for k in ('username', 'first_name'):
            if body.get(k):
                s.update('users', existing['id'], {k: body[k]})
        return jsonify(s.get('users', existing['id']))
    raw = str(body['telegram_id']) + str(time.time())
    code = base64.b32hexencode(hashlib.sha256(raw.encode()).digest()[:6]).decode().lower()[:8]
    user = s.insert('users', {
        'telegram_id': str(body['telegram_id']),
        'username': body.get('username'),
        'first_name': body.get('first_name'),
        'referral_code': body.get('referral_code') or code,
        'referred_by': body.get('referred_by'),
        'balance_usdt': 0,
        'is_admin': 0,
        'is_banned': 0,
        'platform': 'MT4,MT5',
    })
    return jsonify(user), 201


@bp.route('/users/<int:uid>', methods=['PUT'])
def update_user(uid):
    body = request.get_json(force=True)
    u = s.update('users', uid, body)
    if not u:
        return jsonify({'error': 'not found'}), 404
    return jsonify(u)


@bp.route('/users/<int:uid>', methods=['DELETE'])
def delete_user(uid):
    s.delete('users', uid)
    return jsonify({'ok': True})


@bp.route('/users/find', methods=['GET'])
def find_users():
    args = request.args
    kwargs = {k: v for k, v in args.items()}
    if 'telegram_id' in kwargs:
        kwargs['telegram_id'] = str(kwargs['telegram_id'])
    results = s.find('users', **kwargs) if kwargs else s.all('users')
    return jsonify(results)


@bp.route('/users/<int:uid>/lifetime', methods=['PUT'])
def set_lifetime(uid):
    body = request.get_json(force=True)
    enabled = 1 if body.get('enabled', True) else 0
    products = body.get('products', 'all')
    u = s.update('users', uid, {'lifetime': enabled, 'lifetime_products': products})
    if not u:
        return jsonify({'error': 'not found'}), 404
    return jsonify(u)


@bp.route('/users/by-telegram/<telegram_id>', methods=['GET'])
def by_telegram(telegram_id):
    u = s.find_one('users', telegram_id=str(telegram_id))
    if not u:
        return jsonify({'error': 'not found'}), 404
    return jsonify(u)
