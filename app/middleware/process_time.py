"""Process time middleware for FastAPI"""

import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class ProcessTimeMiddleware(BaseHTTPMiddleware):
    """Add X-Process-Time header to response"""

    async def dispatch(self, request: Request, call_next):
        """Process request and add timing header"""
        start_time = time.time()

        # Process request
        response = await call_next(request)

        # Calculate process time
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = f"{process_time:.4f}"

        return response
