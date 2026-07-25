import os, uuid, base64
from flask import Blueprint, request, jsonify, send_from_directory, send_file

bp = Blueprint('files', __name__)

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads', 'eas')


@bp.route('/files/upload', methods=['POST'])
def upload_file():
    if 'file' in request.files:
        f = request.files['file']
        if f.filename == '':
            return jsonify({'error': 'no file selected'}), 400
        product_id = request.form.get('product_id', 'tmp')
        dest = os.path.join(UPLOAD_DIR, str(product_id))
        os.makedirs(dest, exist_ok=True)
        ext = os.path.splitext(f.filename)[1] or '.ex4'
        unique = str(uuid.uuid4())[:8] + ext
        path = os.path.join(dest, unique)
        f.save(path)
    else:
        data = request.get_json()
        if not data or 'filename' not in data or 'data' not in data:
            return jsonify({'error': 'expected file or {filename, data}'}), 400
        raw = base64.b64decode(data['data'])
        product_id = data.get('product_id', 'tmp')
        dest = os.path.join(UPLOAD_DIR, str(product_id))
        os.makedirs(dest, exist_ok=True)
        ext = os.path.splitext(data['filename'])[1] or '.ex4'
        unique = str(uuid.uuid4())[:8] + ext
        path = os.path.join(dest, unique)
        with open(path, 'wb') as f:
            f.write(raw)
    rel = os.path.relpath(path, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return jsonify({'path': rel.replace(os.sep, '/'), 'filename': unique, 'product_id': product_id})


@bp.route('/files/ea/upload', methods=['POST'])
def upload_ea():
    filename = ''
    raw = b''

    if 'file' in request.files:
        f = request.files['file']
        if not f.filename:
            return jsonify({'error': 'no file'}), 400
        filename = f.filename
        raw = f.read()
    else:
        data = request.get_json() or {}
        if 'data' not in data:
            return jsonify({'error': 'send {data, filename}'}), 400
        filename = data.get('filename', 'ea_file.ex4')
        raw = base64.b64decode(data['data'])

    product_id = request.args.get('product_id') or request.form.get('product_id') or (request.get_json() or {}).get('product_id', 'tmp')
    name = request.args.get('name') or filename
    dest = os.path.join(UPLOAD_DIR, str(product_id))
    os.makedirs(dest, exist_ok=True)
    path = os.path.join(dest, name)

    with open(path, 'wb') as f:
        f.write(raw)

    rel = os.path.relpath(path, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return jsonify({'path': rel.replace(os.sep, '/'), 'filename': name, 'product_id': product_id, 'size': len(raw)})


@bp.route('/files/ea/download', methods=['GET'])
def download_ea():
    product_id = request.args.get('product_id', '')
    name = request.args.get('name', '')
    if not product_id or not name:
        return jsonify({'error': 'need product_id and name'}), 400
    path = os.path.join(UPLOAD_DIR, str(product_id), name)
    if not os.path.exists(path):
        return jsonify({'error': 'file not found'}), 404
    return send_file(path, as_attachment=True, download_name=name)


@bp.route('/files/ea/list', methods=['GET'])
def list_ea_files():
    product_id = request.args.get('product_id', '')
    base = os.path.join(UPLOAD_DIR, str(product_id)) if product_id else UPLOAD_DIR
    if not os.path.isdir(base):
        return jsonify([])
    files = []
    for root, dirs, fnames in os.walk(base):
        for fname in fnames:
            fp = os.path.join(root, fname)
            rel = os.path.relpath(fp, UPLOAD_DIR)
            files.append({'path': rel.replace(os.sep, '/'), 'name': fname, 'size': os.path.getsize(fp)})
    return jsonify(files)


@bp.route('/files/ea/delete', methods=['DELETE'])
def delete_ea_file():
    data = request.get_json() or {}
    product_id = data.get('product_id') or request.args.get('product_id', '')
    name = data.get('name') or request.args.get('name', '')
    if not product_id or not name:
        return jsonify({'error': 'need product_id and name'}), 400
    path = os.path.join(UPLOAD_DIR, str(product_id), name)
    if not os.path.exists(path):
        return jsonify({'error': 'not found'}), 404
    os.unlink(path)
    return jsonify({'ok': True, 'deleted': name})


@bp.route('/files/download/<path:filepath>', methods=['GET'])
def download_file(filepath):
    full = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), filepath)
    if not os.path.exists(full):
        return jsonify({'error': 'not found'}), 404
    return send_from_directory(os.path.dirname(full), os.path.basename(full))
