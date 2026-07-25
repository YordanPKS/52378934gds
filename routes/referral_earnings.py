from flask import Blueprint, request, jsonify
import storage as s

bp = Blueprint('referral_earnings', __name__)


@bp.route('/referral_earnings', methods=['GET'])
def list_referral_earnings():
    referrer_id = request.args.get('referrer_id')
    order_by = request.args.get('order_by')
    desc = request.args.get('desc', '1') == '1'
    kwargs = {}
    if order_by: kwargs['_order_by'] = order_by; kwargs['_order_desc'] = desc
    if referrer_id: kwargs['referrer_id'] = int(referrer_id)
    results = s.find('referral_earnings', **kwargs) if kwargs else s.all('referral_earnings', order_by=order_by, desc=desc)
    return jsonify(results)


@bp.route('/referral_earnings/<int:rid>', methods=['GET'])
def get_referral_earning(rid):
    r = s.get('referral_earnings', rid)
    if not r:
        return jsonify({'error': 'not found'}), 404
    return jsonify(r)


@bp.route('/referral_earnings', methods=['POST'])
def create_referral_earning():
    body = request.get_json(force=True)
    if not body.get('referrer_id'):
        return jsonify({'error': 'referrer_id required'}), 400
    r = s.insert('referral_earnings', {
        'referrer_id': int(body['referrer_id']),
        'referred_id': body.get('referred_id'),
        'amount_usdt': float(body.get('amount_usdt', 0)),
        'source': body.get('source'),
        'paid': 1 if body.get('paid') else 0,
    })
    return jsonify(r), 201


@bp.route('/referral_earnings/<int:rid>', methods=['PUT'])
def update_referral_earning(rid):
    body = request.get_json(force=True)
    r = s.update('referral_earnings', rid, body)
    if not r:
        return jsonify({'error': 'not found'}), 404
    return jsonify(r)


@bp.route('/referral_earnings/<int:rid>', methods=['DELETE'])
def delete_referral_earning(rid):
    s.delete('referral_earnings', rid)
    return jsonify({'ok': True})
