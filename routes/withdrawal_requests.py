from flask import Blueprint, request, jsonify
import storage as s

bp = Blueprint('withdrawal_requests', __name__)


@bp.route('/withdrawal_requests', methods=['GET'])
def list_withdrawal_requests():
    user_id = request.args.get('user_id')
    status = request.args.get('status')
    order_by = request.args.get('order_by')
    desc = request.args.get('desc', '1') == '1'
    kwargs = {}
    if order_by: kwargs['_order_by'] = order_by; kwargs['_order_desc'] = desc
    if user_id: kwargs['user_id'] = int(user_id)
    if status: kwargs['status'] = status
    results = s.find('withdrawal_requests', **kwargs) if kwargs else s.all('withdrawal_requests', order_by=order_by, desc=desc)
    return jsonify(results)


@bp.route('/withdrawal_requests/<int:wid>', methods=['GET'])
def get_withdrawal_request(wid):
    w = s.get('withdrawal_requests', wid)
    if not w:
        return jsonify({'error': 'not found'}), 404
    return jsonify(w)


@bp.route('/withdrawal_requests', methods=['POST'])
def create_withdrawal_request():
    body = request.get_json(force=True)
    if not body.get('user_id') or not body.get('amount_usdt'):
        return jsonify({'error': 'user_id and amount_usdt required'}), 400
    w = s.insert('withdrawal_requests', {
        'user_id': int(body['user_id']),
        'amount_usdt': float(body['amount_usdt']),
        'wallet_address': body.get('wallet_address', ''),
        'status': body.get('status', 'pending'),
    })
    return jsonify(w), 201


@bp.route('/withdrawal_requests/<int:wid>', methods=['PUT'])
def update_withdrawal_request(wid):
    body = request.get_json(force=True)
    w = s.update('withdrawal_requests', wid, body)
    if not w:
        return jsonify({'error': 'not found'}), 404
    return jsonify(w)


@bp.route('/withdrawal_requests/<int:wid>', methods=['DELETE'])
def delete_withdrawal_request(wid):
    s.delete('withdrawal_requests', wid)
    return jsonify({'ok': True})
