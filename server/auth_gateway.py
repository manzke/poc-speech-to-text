"""Auth gateway for the STT service (ingress auth, PRD §13).

WhisperLiveKit has no built-in authentication. Rather than fork it or sit a
proxy in the audio hot path, this is a tiny validator designed to run behind an
ingress sub-request (nginx ``auth-url`` / ``auth_request``): the ingress forwards
every request — including the WebSocket upgrade to ``/asr`` — to ``/auth/verify``
here, and we answer **200** to allow or **401** to deny. The real traffic never
flows through this process, so it adds no streaming latency.

Token sources (checked in order):
  1. ``Authorization: Bearer <token>`` header.
  2. ``?token=<token>`` in the original request URI (the SDK uses this form
     because browsers cannot set headers on a WebSocket handshake). nginx passes
     the original URI as ``X-Original-URI``.

Modes (env ``STT_AUTH_MODE``):
  ``static`` — constant-time compare against ``STT_AUTH_TOKEN``.
  ``jwt``    — verify a HS256 JWT signed with ``STT_AUTH_JWT_SECRET`` (PyJWT),
               optionally checking ``STT_AUTH_JWT_AUDIENCE`` / ``_ISSUER``.

Run:  python -m uvicorn server.auth_gateway:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Mapping
from urllib.parse import parse_qs, urlsplit

BEARER_PREFIX = "bearer "


def extract_token(authorization: str | None, original_uri: str | None) -> str | None:
    """Pull the token from an Authorization header or a ``?token=`` query."""
    if authorization:
        value = authorization.strip()
        if value.lower().startswith(BEARER_PREFIX):
            return value[len(BEARER_PREFIX):].strip() or None
        # Bare token without the Bearer scheme is also accepted.
        return value or None
    if original_uri:
        query = urlsplit(original_uri).query
        tokens = parse_qs(query).get("token")
        if tokens:
            return tokens[0] or None
    return None


def verify_static(token: str, expected: str) -> bool:
    """Constant-time comparison against the shared secret."""
    if not token or not expected:
        return False
    return hmac.compare_digest(token, expected)


def _b64url_decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def verify_jwt(
    token: str,
    secret: str,
    *,
    audience: str | None = None,
    issuer: str | None = None,
    leeway: int = 0,
) -> bool:
    """Verify a HS256 JWT using only the standard library.

    We require an ``exp`` claim and check ``nbf``/``aud``/``iss`` when relevant.
    Returns False on any malformed token or failed check. HS256 is HMAC-SHA256,
    so no third-party crypto dependency is needed; RS256/JWKS is a future add.
    """
    if not token or not secret:
        return False
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
        header = json.loads(_b64url_decode(header_b64))
        if header.get("alg") != "HS256":
            return False
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(sig_b64)):
            return False

        payload = json.loads(_b64url_decode(payload_b64))
        now = int(time.time())
        if "exp" not in payload or now > int(payload["exp"]) + leeway:
            return False
        if "nbf" in payload and now < int(payload["nbf"]) - leeway:
            return False
        if audience is not None:
            aud = payload.get("aud")
            allowed = aud if isinstance(aud, list) else [aud]
            if audience not in allowed:
                return False
        if issuer is not None and payload.get("iss") != issuer:
            return False
        return True
    except Exception:
        return False


def is_authorized(env: Mapping[str, str], authorization: str | None, original_uri: str | None) -> bool:
    """Top-level decision used by the endpoint; driven entirely by env config."""
    mode = (env.get("STT_AUTH_MODE") or "static").strip().lower()
    token = extract_token(authorization, original_uri)
    if not token:
        return False
    if mode == "static":
        return verify_static(token, env.get("STT_AUTH_TOKEN", ""))
    if mode == "jwt":
        return verify_jwt(
            token,
            env.get("STT_AUTH_JWT_SECRET", ""),
            audience=env.get("STT_AUTH_JWT_AUDIENCE") or None,
            issuer=env.get("STT_AUTH_JWT_ISSUER") or None,
        )
    raise ValueError(f"unknown STT_AUTH_MODE: {mode!r}")


# --- ASGI app (only imported/instantiated when actually run) ------------------
def _build_app():  # pragma: no cover - thin FastAPI wiring, exercised in CI/e2e
    from fastapi import FastAPI, Request, Response

    app = FastAPI(title="stt-auth-gateway", docs_url=None, redoc_url=None)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/auth/verify")
    def verify(request: Request) -> Response:
        try:
            ok = is_authorized(
                os.environ,
                request.headers.get("authorization"),
                request.headers.get("x-original-uri"),
            )
        except ValueError:
            return Response(status_code=500)  # misconfiguration (bad STT_AUTH_MODE)
        return Response(status_code=200 if ok else 401)

    return app


# Lazily create the app so importing this module (e.g. for unit tests) does not
# require FastAPI to be installed.
try:  # pragma: no cover
    app = _build_app()
except Exception:  # pragma: no cover
    app = None
