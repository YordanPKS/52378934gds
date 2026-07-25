from flask import Blueprint, request, jsonify
import storage as s

bp = Blueprint('admin', __name__)


@bp.route('/admin/import', methods=['POST'])
def import_db():
    """Recibe un JSON dump completo y lo inserta en SQLite."""
    body = request.get_json(force=True)
    imported = {}
    for table in ('users', 'products', 'licenses', 'transactions', 'settings', 'referral_earnings', 'withdrawal_requests', 'tickets', 'shared_wallets', 'wallet_keystores', 'bot_states'):
        records = body.get(table, [])
        count = 0
        for rec in records:
            rid = rec.pop('id', None)
            existing = None
            if table == 'settings':
                existing = s.find_one('settings', key=rec.get('key'))
            elif rid:
                existing = s.get(table, rid)
            if existing:
                s.update(table, existing['id'], rec)
            else:
                s.insert(table, rec)
            count += 1
        imported[table] = count
    return jsonify({'ok': True, 'imported': imported})


@bp.route('/admin/export', methods=['GET'])
def export_db():
    """Devuelve todas las tablas como JSON."""
    data = {}
    for table in ('users', 'products', 'licenses', 'transactions', 'settings', 'referral_earnings', 'withdrawal_requests', 'tickets', 'shared_wallets', 'wallet_keystores', 'bot_states'):
        data[table] = s.all(table)
    return jsonify(data)
