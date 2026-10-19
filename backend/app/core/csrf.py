"""Cross-site request forgery guard (Contract §2.1).

Primary control is ``SameSite=Lax`` on the session cookie. As defence in depth,
unsafe methods (POST/PUT/PATCH/DELETE) that carry a ``csm_session`` cookie **and
no ``Authorization: Bearer``** are subject to a same-origin check:

* if ``Origin`` is present, its authority must equal the request ``Host`` (or the
  origin must be whitelisted via ``AUTH_ALLOWED_ORIGINS``);
* else if ``Sec-Fetch-Site`` is present, it must be ``same-origin``;
* if neither header is present (non-browser client), the request is allowed.

Failure returns 403 FORBIDDEN with ``details.reason = "csrf"``.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.security import parse_bearer_authorization, SESSION_COOKIE_NAME

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def _forbidden_csrf() -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={
            "error": {
                "code": "FORBIDDEN",
                "message": "Forbidden",
                "details": {"reason": "csrf"},
            }
        },
    )


def _is_same_origin(request: Request) -> bool:
    settings = get_settings()

    origin = request.headers.get("origin")
    if origin:
        if origin in settings.auth_allowed_origins_list:
            return True
        return urlsplit(origin).netloc == request.headers.get("host", "")

    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site:
        return fetch_site.strip().lower() == "same-origin"

    # Non-browser client with no browser-set headers -> allowed.
    return True


class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method in SAFE_METHODS:
            return await call_next(request)
        # Cookie requests are checked; Bearer requests are exempt (DR-303).
        if not request.cookies.get(SESSION_COOKIE_NAME):
            return await call_next(request)
        bearer_present, _token = parse_bearer_authorization(
            request.headers.get("authorization")
        )
        if bearer_present:
            return await call_next(request)
        if not _is_same_origin(request):
            return _forbidden_csrf()
        return await call_next(request)