import os
import sys

# Ensure the root project directory is in the Python path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import app

import urllib.parse

class VercelPathMiddleware:
    """
    Ensures that when Vercel rewrites requests to /api/index.py,
    Flask receives the real requested URL path (e.g. /, /dashboard, /login, /api/metrics).
    """
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        qs = environ.get("QUERY_STRING", "")
        params = urllib.parse.parse_qs(qs)
        
        # 1. Check if __path__ was forwarded via vercel.json rewrite rule
        if "__path__" in params and params["__path__"]:
            target_path = params["__path__"][0]
            environ["PATH_INFO"] = "/" + target_path.lstrip("/")
            
            # Clean up __path__ so the Flask endpoint only sees clean query params
            del params["__path__"]
            environ["QUERY_STRING"] = urllib.parse.urlencode(params, doseq=True)
        else:
            path_info = environ.get("PATH_INFO", "")
            orig_path = (
                environ.get("HTTP_X_FORWARDED_PATH") or
                environ.get("HTTP_X_MATCHED_PATH") or
                environ.get("HTTP_X_FORWARDED_URI") or
                environ.get("RAW_URI") or
                ""
            )
            
            if orig_path and not orig_path.startswith("/api/index"):
                environ["PATH_INFO"] = "/" + orig_path.split("?")[0].lstrip("/")
            elif path_info in ("/api/index", "/api/index.py", "/api/", "/api"):
                environ["PATH_INFO"] = "/"

        return self.wsgi_app(environ, start_response)

# Wrap WSGI application
app.wsgi_app = VercelPathMiddleware(app.wsgi_app)
app.debug = False

# For direct local testing: python api/index.py
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
