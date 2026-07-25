from flask import Blueprint, request, jsonify
import storage as s

bp = Blueprint('settings', __name__)


@bp.route('/settings', methods=['GET'])
def list_settings():
    return jsonify(s.all('settings'))


@bp.route('/settings/<key>', methods=['GET'])
def get_setting(key):
    entry = s.find_one('settings', key=key)
    if not entry:
        return jsonify({'value': None})
    return jsonify({'key': key, 'value': entry['value']})


@bp.route('/settings/<key>', methods=['PUT'])
def set_setting(key):
    body = request.get_json(force=True)
    val = body.get('value', '')
    existing = s.find_one('settings', key=key)
    if existing:
        s.update('settings', existing['id'], {'value': val})
    else:
        s.insert('settings', {'key': key, 'value': val})
    return jsonify({'key': key, 'value': val})
