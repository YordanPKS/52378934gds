import json
from datetime import datetime
from flask import Blueprint, request, jsonify, Response as FlaskResponse
import storage as s

bp = Blueprint('admin', __name__)


@bp.route('/admin/import', methods=['POST'])
def import_db():
    body = request.get_json(force=True)
    return jsonify(_import_dump(body))


@bp.route('/admin/export', methods=['GET'])
def export_db():
    data = _export_all()
    return jsonify(data)


@bp.route('/admin/export/download', methods=['GET'])
def export_download():
    data = _export_all()
    raw = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    name = f'ea_store_export_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.json'
    return FlaskResponse(raw, mimetype='application/json', headers={
        'Content-Disposition': f'attachment; filename={name}'
    })


@bp.route('/admin/import/upload', methods=['POST'])
def import_upload():
    body = request.get_json(silent=True) or {}
    if 'file' in request.files:
        raw = request.files['file'].read()
    elif body.get('data'):
        import base64
        raw = base64.b64decode(body['data'])
    elif body.get('raw'):
        raw = body['raw'].encode() if isinstance(body['raw'], str) else body['raw']
    else:
        return jsonify({'error': 'send file or {data: base64}'}), 400
    try:
        dump = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        return jsonify({'error': f'Invalid JSON: {e}'}), 400
    return jsonify(_import_dump(dump))


_PANELS = ('users', 'products', 'licenses', 'transactions', 'settings',
           'referral_earnings', 'withdrawal_requests', 'tickets',
           'shared_wallets', 'wallet_keystores', 'bot_states')


def _export_all():
    data = {}
    for table in _PANELS:
        data[table] = s.all(table)
    return data


def _import_dump(dump):
    imported = {}
    for table in _PANELS:
        records = dump.get(table, [])
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
    return {'ok': True, 'imported': imported}


_PANEL_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>db-api Backup Panel</title>
<style>
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#0f0f13; color:#e4e4e7; display:flex; align-items:center; justify-content:center; min-height:100vh; padding:20px; }
  .card { background:#1a1a24; border-radius:16px; padding:32px; max-width:480px; width:100%; box-shadow:0 8px 32px rgba(0,0,0,0.4); }
  h1 { font-size:20px; font-weight:600; margin-bottom:4px; }
  .sub { color:#888; font-size:13px; margin-bottom:24px; }
  .section { margin-bottom:20px; padding:16px; background:#23232f; border-radius:12px; }
  .section h2 { font-size:14px; font-weight:600; margin-bottom:8px; }
  .section p { font-size:12px; color:#888; margin-bottom:12px; }
  .btn { display:inline-flex; align-items:center; gap:6px; padding:10px 20px; border-radius:10px; font-size:14px; font-weight:500; cursor:pointer; border:none; transition:all .2s; text-decoration:none; }
  .btn-primary { background:#3b82f6; color:#fff; }
  .btn-primary:hover { background:#2563eb; }
  .btn-outline { background:transparent; border:1px solid #3b82f6; color:#3b82f6; }
  .btn-outline:hover { background:rgba(59,130,246,0.1); }
  .btn-success { background:#22c55e; color:#fff; }
  .btn-success:hover { background:#16a34a; }
  .btn-danger { background:#ef4444; color:#fff; }
  .btn-danger:hover { background:#dc2626; }
  input[type=file] { display:none; }
  #result { font-size:12px; margin-top:12px; padding:10px; border-radius:8px; min-height:20px; word-break:break-all; }
  #result.ok { background:rgba(34,197,94,0.1); color:#22c55e; }
  #result.err { background:rgba(239,68,68,0.1); color:#ef4444; }
  #result.info { background:rgba(59,130,246,0.1); color:#3b82f6; }
  .footer { margin-top:16px; font-size:11px; color:#555; text-align:center; }
</style>
</head>
<body>
<div class="card">
  <h1>&#x1f4e6; db-api Backup</h1>
  <p class="sub">Export / Import JSON de la base de datos</p>

  <div class="section">
    <h2>&#x2b07;&#xfe0f; Exportar</h2>
    <p>Descarg&aacute; un snapshot completo de la base de datos en JSON.</p>
    <button class="btn btn-primary" onclick="downloadExport()">&#x2b07;&#xfe0f; Descargar JSON</button>
  </div>

  <div class="section">
    <h2>&#x2b06;&#xfe0f; Importar</h2>
    <p>Seleccion&aacute; un archivo JSON exportado previamente para restaurar la base de datos.</p>
    <label class="btn btn-outline" style="cursor:pointer">
      &#x1f4c2; Seleccionar archivo
      <input type="file" accept=".json" onchange="uploadImport(this)">
    </label>
  </div>

  <div id="result"></div>
  <div class="footer">db-api &mdash; <span id="tables-info"></span></div>
</div>

<script>
async function downloadExport() {
  const el = document.getElementById('result');
  el.className = 'info'; el.textContent = 'Descargando...';
  const a = document.createElement('a');
  a.href = '/api/admin/export/download';
  a.download = '';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  el.textContent = '\\u2705 Descarga iniciada';
  setTimeout(() => { el.className = ''; el.textContent = ''; }, 3000);
}

async function uploadImport(input) {
  const file = input.files?.[0];
  if (!file) return;
  const el = document.getElementById('result');
  el.className = 'info'; el.textContent = 'Subiendo e importando...';
  const fd = new FormData();
  fd.append('file', file);
  try {
    const r = await fetch('/api/admin/import/upload', { method: 'POST', body: fd });
    const j = await r.json();
    if (j.ok) {
      el.className = 'ok';
      el.textContent = '\\u2705 Importado: ' + JSON.stringify(j.imported || {});
    } else {
      el.className = 'err';
      el.textContent = '\\u274c ' + (j.error || 'Error');
    }
  } catch(e) {
    el.className = 'err';
    el.textContent = '\\u274c ' + e.message;
  }
  input.value = '';
}

fetch('/api/admin/export').then(r => r.json()).then(d => {
  const total = Object.values(d).reduce((a, b) => a + (Array.isArray(b) ? b.length : 0), 0);
  document.getElementById('tables-info').textContent = Object.keys(d).length + ' tablas, ' + total + ' registros';
}).catch(() => {});
</script>
</body>
</html>
"""
