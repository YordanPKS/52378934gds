from flask import Blueprint, request, jsonify
import storage as s

bp = Blueprint('tickets', __name__)


@bp.route('/tickets', methods=['GET'])
def list_tickets():
    user_id = request.args.get('user_id')
    status = request.args.get('status')
    order_by = request.args.get('order_by')
    desc = request.args.get('desc', '1') == '1'
    kwargs = {}
    if order_by: kwargs['_order_by'] = order_by; kwargs['_order_desc'] = desc
    if user_id: kwargs['user_id'] = int(user_id)
    if status: kwargs['status'] = status
    results = s.find('tickets', **kwargs) if kwargs else s.all('tickets', order_by=order_by, desc=desc)
    return jsonify(results)


@bp.route('/tickets/<int:tid>', methods=['GET'])
def get_ticket(tid):
    t = s.get('tickets', tid)
    if not t:
        return jsonify({'error': 'not found'}), 404
    return jsonify(t)


@bp.route('/tickets', methods=['POST'])
def create_ticket():
    body = request.get_json(force=True)
    if not body.get('user_id') or not body.get('message'):
        return jsonify({'error': 'user_id and message required'}), 400
    t = s.insert('tickets', {
        'user_id': int(body['user_id']),
        'subject': body.get('subject', body['message'][:100]),
        'message': body['message'],
        'replies': body.get('replies', []),
        'status': body.get('status', 'open'),
        'updated_at': body.get('updated_at'),
    })
    return jsonify(t), 201


@bp.route('/tickets/<int:tid>', methods=['PUT'])
def update_ticket(tid):
    body = request.get_json(force=True)
    t = s.update('tickets', tid, body)
    if not t:
        return jsonify({'error': 'not found'}), 404
    return jsonify(t)


@bp.route('/tickets/<int:tid>', methods=['DELETE'])
def delete_ticket(tid):
    s.delete('tickets', tid)
    return jsonify({'ok': True})
