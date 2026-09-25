"""
The webhook stubs in this module are purely for documentation purposes only, using
FastAPI / OpenAPI's standard webhook documentation feature. These are only intended to help guide any user
integrations to other services they maintain. Particularly useful for user-defined download client interactions.

See also: https://fastapi.tiangolo.com/advanced/openapi-webhooks/#an-app-with-webhooks
"""

from beetkeeper.api.webhooks.webhooks import webhook_router

__all__ = ["webhook_router"]
