from flask import Blueprint, request, jsonify
import storage as s

bp = Blueprint('wallet_keystores', __name__)


@bp.route('/wallet_keystores', methods=['GET'])
def list_wallet_keystores():
    return jsonify(s.all('wallet_keystores'))


@bp.route('/wallet_keystores/<int:wid>', methods=['GET'])
def get_wallet_keystore(wid):
    w = s.get('wallet_keystores', wid)
    if not w:
        return jsonify({'error': 'not found'}), 404
    return jsonify(w)


@bp.route('/wallet_keystores', methods=['POST'])
def create_wallet_keystore():
    body = request.get_json(force=True)
    if not body.get('label') or not body.get('address') or not body.get('keystore_json'):
        return jsonify({'error': 'label, address and keystore_json required'}), 400
    w = s.insert('wallet_keystores', {
        'label': body['label'],
        'address': body['address'],
        'keystore_json': body['keystore_json'],
    })
    return jsonify(w), 201


@bp.route('/wallet_keystores/<int:wid>', methods=['DELETE'])
def delete_wallet_keystore(wid):
    s.delete('wallet_keystores', wid)
    return jsonify({'ok': True})
