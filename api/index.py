import os

# The Vercel entry is always the public, stateless demo.
os.environ.setdefault("DEMO_MODE", "1")

from app.main import app  # noqa: E402,F401
