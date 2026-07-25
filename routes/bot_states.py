from datetime import datetime
from flask import Blueprint, request, jsonify
import storage as s

bp = Blueprint('bot_states', __name__)


@bp.route('/bot_states', methods=['GET'])
def list_bot_states():
    chat_id = request.args.get('chat_id')
    state_type = request.args.get('state_type')
    if chat_id and state_type:
        return jsonify(s.find('bot_states', chat_id=chat_id, state_type=state_type))
    if chat_id:
        return jsonify(s.find('bot_states', chat_id=chat_id))
    if state_type:
        return jsonify(s.find('bot_states', state_type=state_type))
    return jsonify(s.all('bot_states'))


@bp.route('/bot_states/<int:bid>', methods=['GET'])
def get_bot_state(bid):
    bs = s.get('bot_states', bid)
    if not bs:
        return jsonify({'error': 'not found'}), 404
    return jsonify(bs)


@bp.route('/bot_states', methods=['POST'])
def create_bot_state():
    body = request.get_json(force=True)
    if not body.get('chat_id') or not body.get('state_type'):
        return jsonify({'error': 'chat_id and state_type required'}), 400
    existing = s.find_one('bot_states', chat_id=str(body['chat_id']), state_type=body['state_type'])
    if existing:
        bs = s.update('bot_states', existing['id'], {
            'state_data': body.get('state_data'),
            'updated_at': datetime.utcnow().isoformat(),
        })
        return jsonify(bs)
    bs = s.insert('bot_states', {
        'chat_id': str(body['chat_id']),
        'state_type': body['state_type'],
        'state_data': body.get('state_data'),
    })
    return jsonify(bs), 201


@bp.route('/bot_states/<int:bid>', methods=['PUT'])
def update_bot_state(bid):
    body = request.get_json(force=True)
    if body.get('state_data') is not None:
        body['state_data'] = body['state_data']
    body['updated_at'] = datetime.utcnow().isoformat()
    bs = s.update('bot_states', bid, body)
    if not bs:
        return jsonify({'error': 'not found'}), 404
    return jsonify(bs)


@bp.route('/bot_states/delete', methods=['POST'])
def delete_bot_states():
    body = request.get_json(force=True) or {}
    chat_id = body.get('chat_id')
    state_type = body.get('state_type')
    if chat_id and state_type:
        existing = s.find('bot_states', chat_id=str(chat_id), state_type=state_type)
        for bs in existing:
            s.delete('bot_states', bs['id'])
        return jsonify({'ok': True, 'deleted': len(existing)})
    return jsonify({'error': 'chat_id and state_type required'}), 400


@bp.route('/bot_states/<int:bid>', methods=['DELETE'])
def delete_bot_state(bid):
    s.delete('bot_states', bid)
    return jsonify({'ok': True})
