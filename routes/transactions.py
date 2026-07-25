from flask import Blueprint, request, jsonify
import storage as s

bp = Blueprint('transactions', __name__)


@bp.route('/transactions', methods=['GET'])
def list_transactions():
    user_id = request.args.get('user_id')
    status = request.args.get('status')
    order_by = request.args.get('order_by')
    desc = request.args.get('desc', '1') == '1'
    kwargs = {}
    if order_by: kwargs['_order_by'] = order_by; kwargs['_order_desc'] = desc
    if user_id: kwargs['user_id'] = int(user_id)
    if status: kwargs['status'] = status
    results = s.find('transactions', **kwargs) if kwargs else s.all('transactions', order_by=order_by, desc=desc)
    return jsonify(results)


@bp.route('/transactions/<int:tid>', methods=['GET'])
def get_transaction(tid):
    t = s.get('transactions', tid)
    if not t:
        return jsonify({'error': 'not found'}), 404
    return jsonify(t)


@bp.route('/transactions', methods=['POST'])
def create_transaction():
    body = request.get_json(force=True)
    if not body.get('user_id'):
        return jsonify({'error': 'user_id required'}), 400
    tx = s.insert('transactions', {
        'user_id': int(body['user_id']),
        'product_id': body.get('product_id'),
        'plan_id': body.get('plan_id'),
        'license_id': body.get('license_id'),
        'product_name': body.get('product_name'),
        'plan_label': body.get('plan_label'),
        'amount_usdt': float(body.get('amount_usdt', 0)),
        'currency': body.get('currency', 'USDT'),
        'tx_hash': body.get('tx_hash'),
        'status': body.get('status', 'pending'),
        'license_key': body.get('license_key'),
        'confirmed_at': body.get('confirmed_at'),
    })
    return jsonify(tx), 201


@bp.route('/transactions/<int:tid>', methods=['PUT'])
def update_transaction(tid):
    body = request.get_json(force=True)
    t = s.update('transactions', tid, body)
    if not t:
        return jsonify({'error': 'not found'}), 404
    return jsonify(t)


@bp.route('/transactions/<int:tid>', methods=['DELETE'])
def delete_transaction(tid):
    s.delete('transactions', tid)
    return jsonify({'ok': True})
