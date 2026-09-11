"""Convenience launcher: `python run.py [port]` starts uvicorn on the app.

Run from anywhere: the `backend/` directory is added to sys.path so the `app`
package resolves regardless of the working directory or PYTHONPATH (covers
`start`-launched windows and the embedded runtime).
"""
import sys
from pathlib import Path

# ensure `backend/` (this file's dir) is importable -> `from app import ...`
_BACKEND = Path(__file__).resolve().parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import uvicorn

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000

if __name__ == "__main__":
    from app.main import app
    uvicorn.run(app, host="0.0.0.0", port=PORT, reload=False)
