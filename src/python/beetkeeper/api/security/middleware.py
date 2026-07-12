import base64
import secrets
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

# Configuration constants
API_USERNAME = "admin"
API_PASSWORD = "supersecretpassword"


class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Allow internal FastAPI documentation to bypass authentication if desired
        if request.url.path in ["/docs", "/openapi.json", "/redoc"]:
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        
        if not auth_header or not auth_header.startswith("Basic "):
            return self._unauthorized_response()

        try:  # TODO[Claude]: See if there's a cleaner, more accepted way of extracting the username and password
            encoded_credentials = auth_header.split(" ")[1]
            decoded_bytes = base64.b64decode(encoded_credentials)
            decoded_str = decoded_bytes.decode("utf-8")
            username, password = decoded_str.split(":", 1)
        except Exception:
            return self._unauthorized_response()

        # 4. Use secrets.compare_digest to prevent timing attacks
        is_valid_username = secrets.compare_digest(username, API_USERNAME)
        is_valid_password = secrets.compare_digest(password, API_PASSWORD)

        if not (is_valid_username and is_valid_password):
            return self._unauthorized_response()

        # 5. Credentials match, proceed to the application logic
        return await call_next(request)

    def _unauthorized_response(self) -> StarletteResponse:
        """Helper to return an HTTP 401 response prompting for basic auth."""
        return StarletteResponse(
            content="Unauthorized",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Restricted Area"'}
        )

# # Register the custom middleware to the application context
# app

# @app.get("/")
# async def read_root():
#     return {"message": "Welcome to the secure section!"}
