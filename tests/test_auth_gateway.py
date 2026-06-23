"""Unit tests for the auth gateway's pure validation logic.

Static mode needs no third-party deps. JWT tests are skipped if PyJWT is absent.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import pytest

from server import auth_gateway as ag


def make_jwt(payload: dict, secret: str, alg: str = "HS256") -> str:
    """Minimal stdlib HS256 JWT encoder for tests (no PyJWT dependency)."""
    def seg(obj) -> str:
        raw = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    header_b64 = seg({"alg": alg, "typ": "JWT"})
    payload_b64 = seg(payload)
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")
    return f"{header_b64}.{payload_b64}.{sig_b64}"


# --- token extraction --------------------------------------------------------
def test_extract_from_bearer_header():
    assert ag.extract_token("Bearer abc123", None) == "abc123"
    assert ag.extract_token("bearer abc123", None) == "abc123"


def test_extract_bare_header_without_scheme():
    assert ag.extract_token("rawtoken", None) == "rawtoken"


def test_extract_from_query_uri():
    assert ag.extract_token(None, "/asr?mode=dictation&token=xyz") == "xyz"


def test_header_takes_precedence_over_uri():
    assert ag.extract_token("Bearer fromheader", "/asr?token=fromuri") == "fromheader"


def test_extract_none_when_absent():
    assert ag.extract_token(None, "/asr?mode=dictation") is None
    assert ag.extract_token(None, None) is None


# --- static mode -------------------------------------------------------------
def test_static_match_and_mismatch():
    assert ag.verify_static("s3cret", "s3cret") is True
    assert ag.verify_static("nope", "s3cret") is False
    assert ag.verify_static("", "s3cret") is False
    assert ag.verify_static("s3cret", "") is False


def test_is_authorized_static():
    env = {"STT_AUTH_MODE": "static", "STT_AUTH_TOKEN": "s3cret"}
    assert ag.is_authorized(env, "Bearer s3cret", None) is True
    assert ag.is_authorized(env, None, "/asr?token=s3cret") is True
    assert ag.is_authorized(env, "Bearer wrong", None) is False
    assert ag.is_authorized(env, None, None) is False


def test_default_mode_is_static():
    assert ag.is_authorized({"STT_AUTH_TOKEN": "t"}, "Bearer t", None) is True


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        ag.is_authorized({"STT_AUTH_MODE": "ldap"}, "Bearer t", None)


# --- jwt mode (stdlib HS256, no external deps) -------------------------------
def test_jwt_valid():
    secret = "topsecret"
    token = make_jwt({"sub": "u1", "exp": int(time.time()) + 60}, secret)
    assert ag.verify_jwt(token, secret) is True


def test_jwt_expired_rejected():
    secret = "topsecret"
    token = make_jwt({"sub": "u1", "exp": int(time.time()) - 10}, secret)
    assert ag.verify_jwt(token, secret) is False


def test_jwt_wrong_secret_rejected():
    token = make_jwt({"sub": "u1", "exp": int(time.time()) + 60}, "right")
    assert ag.verify_jwt(token, "wrong") is False


def test_jwt_requires_exp():
    secret = "topsecret"
    token = make_jwt({"sub": "u1"}, secret)  # no exp
    assert ag.verify_jwt(token, secret) is False


def test_jwt_tampered_payload_rejected():
    secret = "s"
    header_b64, _payload_b64, sig_b64 = make_jwt(
        {"sub": "u1", "exp": int(time.time()) + 60}, secret
    ).split(".")
    forged = base64.urlsafe_b64encode(
        json.dumps({"sub": "admin", "exp": int(time.time()) + 60}).encode()
    ).rstrip(b"=").decode()
    assert ag.verify_jwt(f"{header_b64}.{forged}.{sig_b64}", secret) is False


def test_jwt_non_hs256_rejected():
    # alg "none" / RS256 must not be accepted by the HS256 verifier.
    secret = "s"
    token = make_jwt({"sub": "u1", "exp": int(time.time()) + 60}, secret, alg="none")
    assert ag.verify_jwt(token, secret) is False


def test_jwt_audience_issuer():
    secret = "s"
    token = make_jwt(
        {"sub": "u1", "exp": int(time.time()) + 60, "aud": "stt", "iss": "idp"}, secret
    )
    assert ag.verify_jwt(token, secret, audience="stt", issuer="idp") is True
    assert ag.verify_jwt(token, secret, audience="other") is False


def test_is_authorized_jwt_mode():
    secret = "s"
    env = {"STT_AUTH_MODE": "jwt", "STT_AUTH_JWT_SECRET": secret}
    token = make_jwt({"sub": "u1", "exp": int(time.time()) + 60}, secret)
    assert ag.is_authorized(env, f"Bearer {token}", None) is True
    assert ag.is_authorized(env, None, f"/asr?token={token}") is True
    assert ag.is_authorized(env, "Bearer garbage", None) is False
