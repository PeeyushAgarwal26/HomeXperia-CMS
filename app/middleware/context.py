import time
import uuid

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.context import RequestContext, set_request_context
from app.common.logging import get_logger

logger = get_logger(__name__)


class RequestContextMiddleware:
    """Plain ASGI middleware, not a BaseHTTPMiddleware subclass - the latter
    has a well-documented Starlette gotcha where an exception raised inside
    a route handler, once it propagates back up through call_next(), skips
    the app's registered @app.exception_handler(Exception) entirely and
    hits Starlette's own raw ServerErrorMiddleware instead, which returned
    a full traceback (with local filesystem paths) straight into the HTTP
    response body. A raw ASGI middleware sits at the protocol level instead
    of wrapping call_next, so it doesn't interfere with exception-handler
    dispatch the same way.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
        context = RequestContext(
            trace_id=trace_id,
            path=request.url.path,
            method=request.method,
            client_ip=request.client.host if request.client else "",
        )
        set_request_context(context)

        status_code = 500
        start = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-trace-id", trace_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            duration_ms=duration_ms,
        )
