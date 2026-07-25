from io import BytesIO


class ForceJsonMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        ct = environ.get('CONTENT_TYPE', '')
        if not ct or 'form-urlencoded' in ct or 'text/plain' in ct:
            try:
                length = int(environ.get('CONTENT_LENGTH', '0'))
                if length > 0:
                    body = environ['wsgi.input'].read(length)
                    if body and body[0:1] == b'{':
                        environ['CONTENT_TYPE'] = 'application/json'
                    environ['wsgi.input'] = BytesIO(body)
            except Exception:
                pass
        return self.app(environ, start_response)
