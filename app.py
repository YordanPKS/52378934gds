import os, sys, logging, threading, time, requests

_pkg_dir = os.path.dirname(os.path.abspath(__file__))
_proj = os.path.dirname(_pkg_dir)
if _proj not in sys.path:
    sys.path.append(_proj)
if _pkg_dir not in sys.path:
    sys.path.append(_pkg_dir)

from flask import Flask, jsonify, request, render_template_string
import storage
from middleware import ForceJsonMiddleware
from routes import (
    users, products, settings, admin, plans, shared_wallets,
    licenses, transactions, referral_earnings, withdrawal_requests,
    tickets, files, wallet_keystores, bot_states, backup_server, code_update,
)

logger = logging.getLogger(__name__)

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

    for bp in (users.bp, products.bp, settings.bp, admin.bp, plans.bp,
               shared_wallets.bp, licenses.bp, transactions.bp,
               referral_earnings.bp, withdrawal_requests.bp, tickets.bp,
               files.bp, wallet_keystores.bp, bot_states.bp, backup_server.bp,
               code_update.bp):
        app.register_blueprint(bp, url_prefix='/api')

    @app.route('/panel')
    def panel():
        return render_template_string(admin._PANEL_HTML)

    @app.route('/')
    def index():
        return jsonify({'status': 'ok', 'service': 'db-api'})

    @app.route('/api/health', methods=['GET'])
    def health():
        return jsonify({'status': 'ok', 'db': 'sqlite'})

    @app.errorhandler(500)
    def handle_500(e):
        logger.exception('Internal error')
        return jsonify({'error': str(e)}), 500

    start_auto_pull()
    logger.info('db_api iniciado con todos los blueprints')
    return app


app = create_app()
app.wsgi_app = ForceJsonMiddleware(app.wsgi_app)

if __name__ == '__main__':
    port = int(os.environ.get('DB_API_PORT', 5100))
    app.run(host='0.0.0.0', port=port, debug=True)
