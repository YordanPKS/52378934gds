from flask import Blueprint, request, jsonify
import storage as s

bp = Blueprint('licenses', __name__)


@bp.route('/licenses', methods=['GET'])
def list_licenses():
    user_id = request.args.get('user_id')
    product_id = request.args.get('product_id')
    status = request.args.get('status')
    order_by = request.args.get('order_by')
    desc = request.args.get('desc', '1') == '1'
    kwargs = {}
    if order_by: kwargs['_order_by'] = order_by; kwargs['_order_desc'] = desc
    if user_id: kwargs['user_id'] = int(user_id)
    if product_id: kwargs['product_id'] = int(product_id)
    if status: kwargs['status'] = status
    results = s.find('licenses', **kwargs) if kwargs else s.all('licenses', order_by=order_by, desc=desc)
    return jsonify(results)


@bp.route('/licenses/<int:lid>', methods=['GET'])
def get_license(lid):
    l = s.get('licenses', lid)
    if not l:
        return jsonify({'error': 'not found'}), 404
    return jsonify(l)


@bp.route('/licenses', methods=['POST'])
def create_license():
    body = request.get_json(force=True)
    if not body.get('user_id') or not body.get('license_key'):
        return jsonify({'error': 'user_id and license_key required'}), 400
    lic = s.insert('licenses', {
        'user_id': int(body['user_id']),
        'product_id': int(body.get('product_id', 0)),
        'plan_id': body.get('plan_id'),
        'plan_label': body.get('plan_label'),
        'plan_duration_days': body.get('plan_duration_days'),
        'license_key': body['license_key'],
        'transaction_id': body.get('transaction_id'),
        'status': body.get('status', 'active'),
        'activated_accounts': body.get('activated_accounts', []),
        'assigned_account': body.get('assigned_account'),
        'expires_at': body.get('expires_at'),
    })
    return jsonify(lic), 201


@bp.route('/licenses/<int:lid>', methods=['PUT'])
def update_license(lid):
    body = request.get_json(force=True)
    l = s.update('licenses', lid, body)
    if not l:
        return jsonify({'error': 'not found'}), 404
    return jsonify(l)


@bp.route('/licenses/<int:lid>', methods=['DELETE'])
def delete_license(lid):
    s.delete('licenses', lid)
    return jsonify({'ok': True})
