"""Simple file server endpoint for backups (PythonAnywhere)."""

import os, json, time, requests
from flask import Blueprint, request, jsonify, send_file

BACKUP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backups')
os.makedirs(BACKUP_DIR, exist_ok=True)

bp = Blueprint('backup_server', __name__)


@bp.route('/backup/upload', methods=['POST'])
def upload_backup():
    if 'file' in request.files:
        f = request.files['file']
        if not f.filename:
            return jsonify({'error': 'empty filename'}), 400
        path = os.path.join(BACKUP_DIR, f.filename)
        f.save(path)
        return jsonify({'ok': True, 'file': f.filename, 'size': os.path.getsize(path)})
    data = request.get_json()
    if not data or 'filename' not in data or 'data' not in data:
        return jsonify({'error': 'expected file or {filename, data}'}), 400
    import base64
    raw = base64.b64decode(data['data'])
    path = os.path.join(BACKUP_DIR, data['filename'])
    with open(path, 'wb') as f:
        f.write(raw)
    return jsonify({'ok': True, 'file': data['filename'], 'size': len(raw)})


@bp.route('/backup/list', methods=['GET'])
def list_backups():
    files = []
    for fn in os.listdir(BACKUP_DIR):
        fp = os.path.join(BACKUP_DIR, fn)
        if os.path.isfile(fp):
            files.append({
                'name': fn,
                'size': os.path.getsize(fp),
                'mtime': os.path.getmtime(fp),
            })
    files.sort(key=lambda x: x['mtime'], reverse=True)
    return jsonify(files)


@bp.route('/backup/download/<filename>', methods=['GET'])
def download_backup(filename):
    path = os.path.join(BACKUP_DIR, filename)
    if not os.path.exists(path):
        return jsonify({'error': 'not found'}), 404
    return send_file(path, as_attachment=True, download_name=filename)


RENDER_URL = 'https://ea-store-telegram.onrender.com'
SYNC_SECRET = 'ea-sync-2026'


@bp.route('/backup/pull', methods=['POST'])
def pull_backup():
    token = request.args.get('token', '')
    if token != SYNC_SECRET:
        return jsonify({'error': 'unauthorized'}), 401
    try:
        r = requests.get(f'{RENDER_URL}/api/backup/sync-download?token={SYNC_SECRET}', timeout=120)
        if r.status_code != 200:
            return jsonify({'error': f'render returned {r.status_code}', 'detail': r.text[:500]}), 502
        content_disposition = r.headers.get('Content-Disposition', '')
        filename = 'ea_store_sync.zip'
        if 'filename=' in content_disposition:
            filename = content_disposition.split('filename=')[-1].split(';')[0].strip('"\' ')
        path = os.path.join(BACKUP_DIR, filename)
        with open(path, 'wb') as f:
            f.write(r.content)
        return jsonify({'ok': True, 'file': filename, 'size': len(r.content)})
    except requests.RequestException as e:
        return jsonify({'error': str(e)}), 502
