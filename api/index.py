import os
import sys

# Ensure the root project directory is in the Python path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app import app

class VercelPathMiddleware:
    """
    Ensures that when Vercel rewrites requests to /api/index.py,
    Flask receives the real requested URL path (e.g. /, /dashboard, /login, /api/metrics).
    """
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path_info = environ.get("PATH_INFO", "")
        
        # Extract the real user-facing path from Vercel edge proxy headers
        orig_path = (
            environ.get("HTTP_X_FORWARDED_PATH") or
            environ.get("HTTP_X_MATCHED_PATH") or
            environ.get("HTTP_X_FORWARDED_URI") or
            environ.get("RAW_URI") or
            ""
        )
        
        # When path_info is the serverless entrypoint (/api/index or /api/index.py)
        if path_info in ("/api/index", "/api/index.py", "/api/", "/api"):
            if orig_path and orig_path not in ("/api/index", "/api/index.py", "/api/", "/api"):
                environ["PATH_INFO"] = orig_path.split("?")[0]
            else:
                environ["PATH_INFO"] = "/"
        elif orig_path and not orig_path.startswith("/api/index"):
            environ["PATH_INFO"] = orig_path.split("?")[0]

        return self.wsgi_app(environ, start_response)

# Wrap WSGI application
app.wsgi_app = VercelPathMiddleware(app.wsgi_app)
app.debug = False

# For direct local testing: python api/index.py
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
