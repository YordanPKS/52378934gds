import os, sys, secrets, logging, threading, time, requests

_pkg_dir = os.path.dirname(os.path.abspath(__file__))
_proj = os.path.dirname(_pkg_dir)
if _proj not in sys.path:
    sys.path.append(_proj)
if _pkg_dir not in sys.path:
    sys.path.append(_pkg_dir)

from flask import Flask, jsonify, request, render_template_string, session, redirect
import storage
from middleware import ForceJsonMiddleware
from auth import require_api_key
from routes import (
    users, products, settings, admin, plans, shared_wallets,
    licenses, transactions, referral_earnings, withdrawal_requests,
    tickets, files, wallet_keystores, bot_states, backup_server, code_update,
    wallet_pool as wallet_pool_routes,
    license_validations,
)
import wallet_pool as wp

logger = logging.getLogger(__name__)

PANEL_USER = 'admin'
PANEL_PASS = 'admin123'


# ─── Auto-pull daemon ──────────────────────────────────

BACKUP_DIR = os.path.join(_pkg_dir, 'backups')
_PULL_INTERVAL = 300
_SYNC_SECRET = 'ea-sync-2026'
_RENDER_URL = 'https://ea-store-telegram.onrender.com'
_pull_stop = threading.Event()
_pull_thread = None


def _auto_pull_loop():
    while not _pull_stop.wait(_PULL_INTERVAL):
        try:
            r = requests.get(f'{_RENDER_URL}/api/backup/sync-download?token={_SYNC_SECRET}', timeout=120)
            if r.status_code != 200:
                logger.warning('Pull from Render: HTTP %s', r.status_code)
                continue
            os.makedirs(BACKUP_DIR, exist_ok=True)
            path = os.path.join(BACKUP_DIR, f'ea_store_sync_{int(time.time())}.zip')
            with open(path, 'wb') as f:
                f.write(r.content)
            logger.info('Pull from Render OK: %s (%d bytes)', path, len(r.content))
        except requests.RequestException as e:
            logger.warning('Pull from Render error: %s', e)


def start_auto_pull():
    global _pull_thread
    if _pull_thread and _pull_thread.is_alive():
        return
    _pull_stop.clear()
    _pull_thread = threading.Thread(target=_auto_pull_loop, daemon=True, name='pa-pull')
    _pull_thread.start()
    logger.info('Auto-pull daemon iniciado (cada %ds)', _PULL_INTERVAL)


# ─── App ───────────────────────────────────────────────

def create_app():
    app = Flask(__name__)
    storage.init_db()

    @app.before_request
    def _fix_content_type():
        if request.method in ('POST', 'PUT', 'PATCH') and request.data and not request.content_type:
            request.environ['CONTENT_TYPE'] = 'application/json'

    @app.before_request
    def _check_auth():
        if request.method == 'OPTIONS':
            return
        if request.path in ('/', '/api/health') or request.path.startswith('/panel'):
            return
        if request.path.startswith('/api/'):
            api_key = os.environ.get('DB_API_KEY', '')
            if not api_key:
                return
            auth = request.headers.get('Authorization', '')
            if auth.startswith('Bearer ') and auth[7:] == api_key:
                return
            return jsonify({'error': 'unauthorized'}), 401

    for bp in (users.bp, products.bp, settings.bp, admin.bp, plans.bp,
               shared_wallets.bp, licenses.bp, transactions.bp,
               referral_earnings.bp, withdrawal_requests.bp, tickets.bp,
               files.bp, wallet_keystores.bp, bot_states.bp, backup_server.bp,
               code_update.bp, wallet_pool_routes.bp, license_validations.bp):
        app.register_blueprint(bp, url_prefix='/api')

    try:
        wp.initialize_pool()
        wp.start_background_scanner()
    except Exception as e:
        logger.warning('Wallet pool init (non-fatal): %s', e)

    app.secret_key = os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32)

    @app.route('/panel', methods=['GET'])
    def panel():
        if not session.get('panel_auth'):
            return render_template_string(_LOGIN_HTML)
        return render_template_string(admin._PANEL_HTML)

    @app.route('/panel/login', methods=['POST'])
    def panel_login():
        data = request.get_json(silent=True) or {}
        pwd = data.get('password', '')
        if pwd == PANEL_PASS:
            session['panel_auth'] = True
            return jsonify({'ok': True})
        logger.warning('Panel login failed: submitted=%s expected=%s', pwd, PANEL_PASS)
        return jsonify({'ok': False, 'error': 'Invalid password'}), 401

    @app.route('/panel/logout', methods=['POST'])
    def panel_logout():
        session.pop('panel_auth', None)
        return jsonify({'ok': True})

    @app.route('/')
    def index():
        return jsonify({'status': 'ok', 'service': 'db-api'})

    @app.route('/api/health', methods=['GET'])
    def health():
        return jsonify({'status': 'ok', 'db': 'sqlite'})

    _COUNT_SUM_TABLES = {'users', 'products', 'plans', 'licenses', 'transactions',
                         'settings', 'referral_earnings', 'withdrawal_requests',
                         'tickets', 'wallet_keystores', 'shared_wallets', 'bot_states',
                         'license_validations'}

    @app.route('/api/<table>/count', methods=['GET'])
    def api_count(table):
        if table not in _COUNT_SUM_TABLES:
            return jsonify({'error': 'not found'}), 404
        kwargs = {}
        for key in request.args:
            kwargs[key] = request.args[key]
        return jsonify(storage.count(table, **kwargs))

    @app.route('/api/<table>/sum', methods=['GET'])
    def api_sum(table):
        if table not in _COUNT_SUM_TABLES:
            return jsonify({'error': 'not found'}), 404
        field = request.args.get('field', '')
        if not field:
            return jsonify({'error': 'field required'}), 400
        kwargs = {k: request.args[k] for k in request.args if k != 'field'}
        return jsonify(storage.sum_field(table, field, **kwargs))

    @app.errorhandler(404)
    def handle_404(e):
        return jsonify({'error': 'not found'}), 404

    @app.errorhandler(405)
    def handle_405(e):
        return jsonify({'error': 'method not allowed'}), 405

    @app.errorhandler(413)
    def handle_413(e):
        return jsonify({'error': 'request entity too large'}), 413

    @app.errorhandler(500)
    def handle_500(e):
        logger.exception('Internal error')
        return jsonify({'error': str(e)}), 500

    @app.after_request
    def _api_json(response):
        if request.path.startswith('/api/'):
            response.content_type = 'application/json'
        return response

    start_auto_pull()

    logger.info('Panel login: user=%s pass=%s', PANEL_USER, PANEL_PASS)
    logger.info('db_api iniciado con todos los blueprints')
    return app


app = create_app()
app.wsgi_app = ForceJsonMiddleware(app.wsgi_app)

_LOGIN_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>db-api Panel</title>
<style>
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#0f0f13; color:#e4e4e7; display:flex; align-items:center; justify-content:center; min-height:100vh; padding:20px; }
  .card { background:#1a1a24; border-radius:16px; padding:32px; max-width:380px; width:100%; box-shadow:0 8px 32px rgba(0,0,0,0.4); text-align:center; }
  h1 { font-size:20px; font-weight:600; margin-bottom:4px; }
  .sub { color:#888; font-size:13px; margin-bottom:24px; }
  input { width:100%; padding:12px 16px; border-radius:10px; border:1px solid #333; background:#23232f; color:#e4e4e7; font-size:15px; outline:none; transition:border .2s; }
  input:focus { border-color:#3b82f6; }
  .btn { width:100%; padding:12px; border-radius:10px; font-size:15px; font-weight:500; cursor:pointer; border:none; margin-top:12px; background:#3b82f6; color:#fff; transition:background .2s; }
  .btn:hover { background:#2563eb; }
  #error { font-size:12px; color:#ef4444; margin-top:10px; min-height:18px; }
</style>
</head>
<body>
<div class="card">
  <h1>&#x1f4e6; db-api Backup</h1>
  <p class="sub">Ingres&aacute; la contrase&ntilde;a del panel</p>
  <input type="password" id="password" placeholder="Contrase&ntilde;a" autofocus onkeydown="if(event.key==='Enter') login()">
  <button class="btn" onclick="login()">Ingresar</button>
  <div id="error"></div>
</div>
<script>
async function login() {
  const pwd = document.getElementById('password').value;
  const el = document.getElementById('error');
  if (!pwd) { el.textContent = 'Ingres&aacute; la contrase&ntilde;a'; return; }
  try {
    const r = await fetch('/panel/login', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({password:pwd}) });
    const j = await r.json();
    if (j.ok) { location.reload(); }
    else { el.textContent = j.error || 'Contrase&ntilde;a incorrecta'; }
  } catch(e) { el.textContent = 'Error de conexi&oacute;n'; }
}
</script>
</body>
</html>
"""

if __name__ == '__main__':
    port = int(os.environ.get('DB_API_PORT', 5100))
    app.run(host='0.0.0.0', port=port, debug=True)
