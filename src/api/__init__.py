"""FastAPI surface for the FinRisk Agent Studio workflow.

The package exposes the ASGI app via :mod:`src.api.main`. Importing
``src.api.main:app`` is sufficient for ``uvicorn`` to serve the API.
"""

from src.api.main import app

__all__ = ["app"]