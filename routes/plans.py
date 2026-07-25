from flask import Blueprint, request, jsonify
import storage as s

bp = Blueprint('plans', __name__)


@bp.route('/plans', methods=['GET'])
def list_plans():
    product_id = request.args.get('product_id')
    if product_id:
        return jsonify(s.find('plans', product_id=int(product_id)))
    return jsonify(s.all('plans'))


@bp.route('/plans/<int:pid>', methods=['GET'])
def get_plan(pid):
    p = s.get('plans', pid)
    if not p:
        return jsonify({'error': 'not found'}), 404
    return jsonify(p)


@bp.route('/plans', methods=['POST'])
def create_plan():
    body = request.get_json(force=True)
    if not body.get('product_id') or not body.get('label'):
        return jsonify({'error': 'product_id and label required'}), 400
    plan = s.insert('plans', {
        'product_id': int(body['product_id']),
        'label': body['label'],
        'duration_days': int(body.get('duration_days', 30)),
        'price_usdt': float(body.get('price_usdt', 0)),
    })
    return jsonify(plan), 201


@bp.route('/plans/<int:pid>', methods=['PUT'])
def update_plan(pid):
    body = request.get_json(force=True)
    p = s.update('plans', pid, body)
    if not p:
        return jsonify({'error': 'not found'}), 404
    return jsonify(p)


@bp.route('/plans/<int:pid>', methods=['DELETE'])
def delete_plan(pid):
    s.delete('plans', pid)
    return jsonify({'ok': True})
