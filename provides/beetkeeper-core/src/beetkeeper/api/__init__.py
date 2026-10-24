"""
This module contains the components necessary for defining `FastAPI` app instance, along with its composite
subrouters, and any static files / HTML templates.
"""

from beetkeeper.api.fastapi_app import create_app

__all__ = ["create_app"]
