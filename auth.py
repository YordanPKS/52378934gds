"""API Key authentication middleware for db-api."""
import os, functools
from flask import request, jsonify

API_KEY = os.environ.get('DB_API_KEY', '')

PUBLIC_PATHS = ('/', '/api/health', '/panel', '/panel/login', '/panel/logout')


def require_api_key(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if request.method == 'OPTIONS':
            return f(*args, **kwargs)
        if request.path in PUBLIC_PATHS or request.path.startswith('/panel'):
            return f(*args, **kwargs)
        auth = request.headers.get('Authorization', '')
        if auth.startswith('Bearer ') and auth[7:] == API_KEY:
            return f(*args, **kwargs)
        return jsonify({'error': 'unauthorized'}), 401
    return wrapper