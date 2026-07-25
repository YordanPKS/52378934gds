from flask import Blueprint, request, jsonify
import storage as s

bp = Blueprint('shared_wallets', __name__)


@bp.route('/shared_wallets', methods=['GET'])
def list_shared_wallets():
    chain = request.args.get('chain')
    order_by = request.args.get('order_by')
    desc = request.args.get('desc', '1') == '1'
    if chain:
        return jsonify(s.find('shared_wallets', chain=chain, _order_by=order_by, _order_desc=desc) if order_by else s.find('shared_wallets', chain=chain))
    return jsonify(s.all('shared_wallets', order_by=order_by, desc=desc))


@bp.route('/shared_wallets/<int:wid>', methods=['GET'])
def get_shared_wallet(wid):
    w = s.get('shared_wallets', wid)
    if not w:
        return jsonify({'error': 'not found'}), 404
    return jsonify(w)


@bp.route('/shared_wallets', methods=['POST'])
def create_shared_wallet():
    body = request.get_json(force=True)
    if not body.get('chain') or not body.get('address'):
        return jsonify({'error': 'chain and address required'}), 400
    existing = s.find_one('shared_wallets', chain=body['chain'])
    if existing:
        return jsonify(existing)
    w = s.insert('shared_wallets', {
        'chain': body['chain'],
        'address': body['address'],
        'secret': body.get('secret', ''),
    })
    return jsonify(w), 201


@bp.route('/shared_wallets/<int:wid>', methods=['PUT'])
def update_shared_wallet(wid):
    body = request.get_json(force=True)
    w = s.update('shared_wallets', wid, body)
    if not w:
        return jsonify({'error': 'not found'}), 404
    return jsonify(w)


@bp.route('/shared_wallets/<int:wid>', methods=['DELETE'])
def delete_shared_wallet(wid):
    s.delete('shared_wallets', wid)
    return jsonify({'ok': True})
