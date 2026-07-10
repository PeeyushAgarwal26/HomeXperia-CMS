import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class RequestContext:
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    admin_user_id: str | None = None
    path: str = ""
    method: str = ""
    client_ip: str = ""


_request_context: ContextVar[RequestContext] = ContextVar("_request_context", default=RequestContext())


def get_request_context() -> RequestContext:
    return _request_context.get()


def set_request_context(context: RequestContext) -> None:
    _request_context.set(context)
