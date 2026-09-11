import os
import sys

# Ensure the root project directory is in the Python path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import app

import re
import urllib.parse

class VercelPathMiddleware:
    """
    Ensures that when Vercel rewrites requests to /api/index.py,
    Flask receives the real requested URL path (e.g. /, /dashboard, /login, /api/metrics, /api/hazards).
    """
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        resolved_path = None

        # 1. Primary check: Vercel headers representing the user's browser URL
        for h in (
            "HTTP_X_MATCHED_PATH",
            "HTTP_X_FORWARDED_PATH",
            "HTTP_X_FORWARDED_URI",
            "RAW_URI",
            "REQUEST_URI",
        ):
            val = environ.get(h, "")
            if (
                val
                and not val.startswith("/api/index")
                and not any(ch in val for ch in ("$", "(", ")", "*", ":"))
            ):
                resolved_path = "/" + val.split("?")[0].lstrip("/")
                break

        # 2. Check x-now-route-matches (e.g. 1=login.html or path=dashboard)
        if not resolved_path:
            route_matches = environ.get("HTTP_X_NOW_ROUTE_MATCHES", "")
            if route_matches:
                try:
                    params = urllib.parse.parse_qs(route_matches)
                    match_val = params.get("1", [""])[0] or params.get("path", [""])[0]
                    if match_val and not any(ch in match_val for ch in ("$", "(", ")", "*")):
                        resolved_path = "/" + match_val.split("?")[0].lstrip("/")
                except Exception:
                    pass

        # 3. Check query string for __path__ injected by rewrites (rejecting $1 placeholders)
        if not resolved_path:
            qs = environ.get("QUERY_STRING", "")
            if qs and "__path__=" in qs:
                params = urllib.parse.parse_qs(qs)
                if "__path__" in params and params["__path__"]:
                    raw_target = params["__path__"][0]
                    clean = urllib.parse.unquote(raw_target).split("?")[0].strip()
                    if clean and not any(ch in clean for ch in ("$", "(", ")", "*", ":")):
                        resolved_path = "/" + clean.lstrip("/")
                    del params["__path__"]
                    environ["QUERY_STRING"] = urllib.parse.urlencode(params, doseq=True)

        # 4. Apply resolved path or preserve valid existing path
        if resolved_path:
            environ["PATH_INFO"] = resolved_path
        else:
            path_info = environ.get("PATH_INFO", "")
            if path_info in ("/api/index", "/api/index.py", "/api/", "/api", ""):
                environ["PATH_INFO"] = "/"

        return self.wsgi_app(environ, start_response)

# Wrap WSGI application once
if not getattr(app, "_vercel_middleware_applied", False):
    app.wsgi_app = VercelPathMiddleware(app.wsgi_app)
    app._vercel_middleware_applied = True
app.debug = False

# For direct local testing: python api/index.py
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
