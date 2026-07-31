from flask import Blueprint, request, jsonify
import storage as s

bp = Blueprint('license_validations', __name__)

_FILTERS = ('license_key', 'license_id', 'product_id', 'ea_id', 'mt4_account', 'result')


@bp.route('/license_validations', methods=['GET'])
def list_validations():
    kwargs = {}
    for k in _FILTERS:
        v = request.args.get(k)
        if v:
            kwargs[k] = int(v) if k in ('license_id', 'product_id') else v
    order = request.args.get('order_by', 'id')
    desc = request.args.get('desc', '1') == '1'
    if kwargs:
        return jsonify(s.find('license_validations', _order_by=order, _order_desc=desc, **kwargs))
    return jsonify(s.all('license_validations', order_by=order, desc=desc))


@bp.route('/license_validations', methods=['POST'])
def create_validation():
    body = request.get_json(force=True)
    if not body.get('license_key'):
        return jsonify({'error': 'license_key required'}), 400
    rec = s.insert('license_validations', {
        'license_key': body.get('license_key'),
        'license_id': body.get('license_id'),
        'product_id': body.get('product_id'),
        'ea_id': body.get('ea_id'),
        'mt4_account': body.get('mt4_account'),
        'ip': body.get('ip'),
        'result': body.get('result', 'valid'),
        'detail': body.get('detail'),
    })
    return jsonify(rec), 201
