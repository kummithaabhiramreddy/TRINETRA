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
    Flask receives the real requested URL path (e.g. /, /dashboard, /login, /api/metrics).
    """
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        # 1. Search for __path__ in RAW_URI, REQUEST_URI, or QUERY_STRING
        resolved_path = None
        for uri_key in ("RAW_URI", "REQUEST_URI", "QUERY_STRING"):
            uri_val = environ.get(uri_key, "")
            if uri_val and "__path__=" in uri_val:
                m = re.search(r"[?&]__path__=([^&]+)", uri_val)
                if m:
                    clean = urllib.parse.unquote(m.group(1)).split("?")[0]
                    resolved_path = "/" + clean.lstrip("/")
                    break

        # 2. Check query string if not found yet
        qs = environ.get("QUERY_STRING", "")
        if qs:
            params = urllib.parse.parse_qs(qs)
            if not resolved_path and "__path__" in params and params["__path__"]:
                resolved_path = "/" + params["__path__"][0].lstrip("/")
            
            # Clean up __path__ from query string
            if "__path__" in params:
                del params["__path__"]
                environ["QUERY_STRING"] = urllib.parse.urlencode(params, doseq=True)

        # 3. Check Vercel proxy headers if still not resolved
        if not resolved_path:
            for h in ("HTTP_X_FORWARDED_PATH", "HTTP_X_MATCHED_PATH", "HTTP_X_FORWARDED_URI"):
                val = environ.get(h, "")
                if val and not val.startswith("/api/index"):
                    resolved_path = "/" + val.split("?")[0].lstrip("/")
                    break

        # 4. Apply resolved path or fallback
        if resolved_path:
            environ["PATH_INFO"] = resolved_path
        else:
            path_info = environ.get("PATH_INFO", "")
            if path_info in ("/api/index", "/api/index.py", "/api/", "/api"):
                environ["PATH_INFO"] = "/"

        return self.wsgi_app(environ, start_response)

# Wrap WSGI application
app.wsgi_app = VercelPathMiddleware(app.wsgi_app)
app.debug = False

# For direct local testing: python api/index.py
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
