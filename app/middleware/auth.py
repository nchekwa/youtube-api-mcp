"""API Key authentication middleware"""

from typing import Optional, List, Union
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from starlette.responses import JSONResponse
from starlette.middleware import Middleware
from app.config import settings

# Get header name from settings (default: X-API-Key)
_header_name = getattr(settings, "APP_X_API_KEY_HEADER", "X-API-Key")
api_key_header = APIKeyHeader(name=_header_name, auto_error=False)

# Parse API key(s) from settings - supports comma-separated list
_env_api_key = getattr(settings, "APP_X_API_KEY", None)

if _env_api_key and "," in _env_api_key:
    # Multiple keys: split by comma and strip whitespace
    API_KEYS: Union[List[str], str, None] = [key.strip() for key in _env_api_key.split(",")]
else:
    API_KEYS = _env_api_key


async def verify_api_key(api_key: Optional[str] = Security(api_key_header)):
    """
    Dependency to verify API key.
    Supports multiple API keys (comma-separated in _APP_X_API_KEY env var).
    If _APP_X_API_KEY is not set, authentication is disabled.
    """
    if API_KEYS:
        if not api_key:
            raise HTTPException(status_code=403, detail="Not authenticated")

        if isinstance(API_KEYS, list):
            if api_key not in API_KEYS:
                raise HTTPException(status_code=401, detail="Invalid API key")
        elif api_key != API_KEYS:
            raise HTTPException(status_code=401, detail="Invalid API key")

    return api_key


def _validate_api_key_value(api_key: Optional[str], api_keys: Union[List[str], str, None]):
    if api_keys:
        if not api_key:
            raise HTTPException(status_code=403, detail="Not authenticated")

        if isinstance(api_keys, list):
            if api_key not in api_keys:
                raise HTTPException(status_code=401, detail="Invalid API key")
        elif api_key != api_keys:
            raise HTTPException(status_code=401, detail="Invalid API key")


class MCPAPIKeyMiddleware:
    def __init__(self, app, api_keys: Union[List[str], str, None], header_name: str | None = None):
        self.app = app
        self.api_keys = api_keys
        self.header_name = (header_name or getattr(settings, "APP_X_API_KEY_HEADER", "X-API-Key")).lower()

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or not self.api_keys:
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        api_key = headers.get(self.header_name)

        try:
            _validate_api_key_value(api_key, self.api_keys)
        except HTTPException as e:
            await JSONResponse({"detail": e.detail}, status_code=e.status_code)(scope, receive, send)
            return

        await self.app(scope, receive, send)


def parse_api_keys(value: str | None) -> Union[List[str], str, None]:
    if not value:
        return None
    if "," in value:
        keys = [k.strip() for k in value.split(",") if k.strip()]
        return keys
    return value


def build_mcp_middleware_from_settings():
    api_keys = parse_api_keys(getattr(settings, "APP_X_API_KEY", ""))
    if not api_keys:
        return None

    return [
        Middleware(
            MCPAPIKeyMiddleware,
            api_keys=api_keys,
            header_name=getattr(settings, "APP_X_API_KEY_HEADER", "X-API-Key"),
        )
    ]
