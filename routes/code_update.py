import os, base64
from flask import Blueprint, request, jsonify

bp = Blueprint('code_update', __name__)

API_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@bp.route('/code/upload', methods=['POST'])
def upload_code():
    files = []

    if 'file' in request.files:
        for f in request.files.getlist('file'):
            if not f.filename.endswith('.py'):
                continue
            raw = f.read()
            rel_path = f.filename.lstrip('/')
            dest = os.path.normpath(os.path.join(API_DIR, rel_path))
            if not dest.startswith(os.path.normpath(API_DIR)):
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, 'wb') as out:
                out.write(raw)
            files.append({'file': rel_path, 'size': len(raw)})

    else:
        data = request.get_json() or {}
        items = data if isinstance(data, list) else [data]
        for item in items:
            rel_path = (item.get('file') or item.get('filename', '')).lstrip('/')
            if not rel_path.endswith('.py'):
                continue
            raw_data = item.get('data', '')
            raw = base64.b64decode(raw_data) if raw_data else b''
            if not raw:
                continue
            dest = os.path.normpath(os.path.join(API_DIR, rel_path))
            if not dest.startswith(os.path.normpath(API_DIR)):
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, 'wb') as out:
                out.write(raw)
            files.append({'file': rel_path, 'size': len(raw)})

    if not files:
        return jsonify({'error': 'no .py files uploaded'}), 400

    return jsonify({'ok': True, 'updated': files})


@bp.route('/code/list', methods=['GET'])
def list_code_files():
    result = []
    for root, dirs, fnames in os.walk(API_DIR):
        for fname in fnames:
            if not fname.endswith('.py'):
                continue
            fp = os.path.join(root, fname)
            rel = os.path.relpath(fp, API_DIR)
            result.append({'file': rel.replace(os.sep, '/'), 'size': os.path.getsize(fp)})
    return jsonify(result)
