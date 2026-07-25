from flask import Blueprint, request, jsonify
import storage as s

bp = Blueprint('products', __name__)


@bp.route('/products', methods=['GET'])
def list_products():
    args = request.args
    if args.get('active_only') == '1':
        return jsonify(s.find('products', is_active=1))
    return jsonify(s.order_by('products', 'created_at', desc=True))


@bp.route('/products/<int:pid>', methods=['GET'])
def get_product(pid):
    p = s.get('products', pid)
    if not p:
        return jsonify({'error': 'not found'}), 404
    return jsonify(p)


@bp.route('/products', methods=['POST'])
def create_product():
    body = request.get_json(force=True)
    if not body.get('name'):
        return jsonify({'error': 'name required'}), 400
    product = s.insert('products', {
        'name': body['name'],
        'description': body.get('description', ''),
        'platform': body.get('platform', 'MT4,MT5'),
        'file_id': body.get('file_id'),
        'file_name': body.get('file_name'),
        'file_url': body.get('file_url'),
        'local_file_path': body.get('local_file_path'),
        'image_url': body.get('image_url'),
        'is_active': body.get('is_active', 1),
        'plans': body.get('plans', []),
    })
    return jsonify(product), 201


@bp.route('/products/<int:pid>', methods=['PUT'])
def update_product(pid):
    body = request.get_json(force=True)
    if body.get('plans'):
        body['plans'] = body['plans']
    p = s.update('products', pid, body)
    if not p:
        return jsonify({'error': 'not found'}), 404
    return jsonify(p)


@bp.route('/products/<int:pid>', methods=['DELETE'])
def delete_product(pid):
    s.delete('products', pid)
    return jsonify({'ok': True})
