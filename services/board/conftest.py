"""Make `app` importable the way the container imports it.

The service runs as `uvicorn app.main:app` with /app as the working directory,
so its own modules are top-level. CI invokes pytest from the repository root,
where they are not. Putting this directory on the path keeps the tests
importing exactly what the container runs, rather than a repo-root package
path that only exists in CI.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
