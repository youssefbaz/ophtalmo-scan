"""API versioning — /api/v1/* is an alias for the canonical /api/* routes.

Strategy: WSGI middleware that rewrites PATH_INFO before Flask's URL
matcher runs. A before_request handler would be too late — Flask matches
URLs in request_context.push(), which runs before any before_request.

Adding this is non-breaking: every /api/foo request continues to work,
and clients that want a stable contract can use /api/v1/foo.
"""


class _ApiV1Middleware:
    """Rewrite /api/v1/<rest> to /api/<rest> at the WSGI boundary."""
    _PREFIX = '/api/v1/'

    def __init__(self, wsgi_app):
        self._wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        if path.startswith(self._PREFIX):
            environ['PATH_INFO'] = '/api/' + path[len(self._PREFIX):]
        return self._wsgi_app(environ, start_response)


def install_api_v1_alias(app) -> None:
    app.wsgi_app = _ApiV1Middleware(app.wsgi_app)
