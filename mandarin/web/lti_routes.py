"""LTI 1.3 routes -- OIDC login initiation and JWT launch.

Implements IMS LTI 1.3 / LTI Advantage for institutional integration.
Requires PyJWT (already a dependency via flask-login).
"""

from __future__ import annotations

import json
import logging
import os
import secrets
from urllib.parse import urlencode

from flask import Blueprint, request, redirect, session, jsonify, url_for

logger = logging.getLogger(__name__)

lti_bp = Blueprint("lti", __name__, url_prefix="/lti")

# Try to import jwt; if unavailable, routes will 501
try:
    import jwt as pyjwt
    import requests as _requests
    _HAS_DEPS = True
except ImportError:
    _HAS_DEPS = False


def _get_platform(conn, issuer: str, client_id: str):
    """Look up an LTI platform registration."""
    return conn.execute(
        "SELECT * FROM lti_platform WHERE issuer = ? AND client_id = ?",
        (issuer, client_id),
    ).fetchone()


@lti_bp.route("/login", methods=["POST", "GET"])
def lti_login():
    """OIDC login initiation (Step 1 of LTI 1.3 launch)."""
    if not _HAS_DEPS:
        return jsonify({"error": "LTI dependencies not installed"}), 501

    from .. import db
    issuer = request.values.get("iss", "")
    client_id = request.values.get("client_id", "")
    login_hint = request.values.get("login_hint", "")
    target_link_uri = request.values.get("target_link_uri", "")
    lti_message_hint = request.values.get("lti_message_hint", "")

    with db.connection() as conn:
        platform = _get_platform(conn, issuer, client_id)

    if not platform:
        logger.warning("lti.unknown_platform", extra={"issuer": issuer, "client_id": client_id})
        return jsonify({"error": "Unknown platform"}), 403

    # Generate state and nonce
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    session["lti_state"] = state
    session["lti_nonce"] = nonce

    # Build OIDC auth request
    params = {
        "scope": "openid",
        "response_type": "id_token",
        "client_id": client_id,
        "redirect_uri": url_for("lti.lti_launch", _external=True),
        "login_hint": login_hint,
        "state": state,
        "response_mode": "form_post",
        "nonce": nonce,
        "prompt": "none",
    }
    if lti_message_hint:
        params["lti_message_hint"] = lti_message_hint

    auth_url = platform["auth_url"] + "?" + urlencode(params)
    return redirect(auth_url)


@lti_bp.route("/launch", methods=["POST"])
def lti_launch():
    """JWT validation and launch (Step 2 of LTI 1.3 launch)."""
    if not _HAS_DEPS:
        return jsonify({"error": "LTI dependencies not installed"}), 501

    from .. import db
    id_token = request.form.get("id_token", "")
    state = request.form.get("state", "")

    # Verify state
    if state != session.pop("lti_state", None):
        return jsonify({"error": "Invalid state"}), 403

    # Decode JWT header to get key ID
    try:
        header = pyjwt.get_unverified_header(id_token)
    except pyjwt.exceptions.DecodeError:
        return jsonify({"error": "Invalid token"}), 400

    # Get claims without verification first to find issuer
    try:
        unverified = pyjwt.decode(id_token, options={"verify_signature": False})
    except Exception:
        return jsonify({"error": "Invalid token"}), 400

    issuer = unverified.get("iss", "")
    client_id = unverified.get("aud", "")
    if isinstance(client_id, list):
        client_id = client_id[0] if client_id else ""

    with db.connection() as conn:
        platform = _get_platform(conn, issuer, client_id)

    if not platform:
        return jsonify({"error": "Unknown platform"}), 403

    # Fetch JWKS and verify token
    try:
        jwks_response = _requests.get(platform["jwks_url"], timeout=10)
        jwks = jwks_response.json()
    except Exception:
        return jsonify({"error": "Failed to fetch platform JWKS"}), 502

    # Find matching key
    kid = header.get("kid")
    public_key = None
    for key_data in jwks.get("keys", []):
        if key_data.get("kid") == kid:
            public_key = pyjwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_data))
            break

    if not public_key:
        return jsonify({"error": "No matching key found"}), 403

    # Verify the token
    try:
        claims = pyjwt.decode(
            id_token,
            public_key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=issuer,
        )
    except pyjwt.exceptions.InvalidTokenError as e:
        logger.warning("lti.invalid_token", extra={"error": str(e)})
        return jsonify({"error": "Token verification failed"}), 403

    # Verify nonce
    expected_nonce = session.pop("lti_nonce", None)
    if claims.get("nonce") != expected_nonce:
        return jsonify({"error": "Invalid nonce"}), 403

    # Verify LTI message type
    msg_type = claims.get("https://purl.imsglobal.org/spec/lti/claim/message_type")
    if msg_type != "LtiResourceLinkRequest":
        return jsonify({"error": f"Unsupported message type: {msg_type}"}), 400

    # Extract user info and create/link account
    lti_sub = claims.get("sub", "")
    email = claims.get("email", "")
    name = claims.get("name", "")

    # Store LTI context in session for the app
    session["lti_user"] = {
        "sub": lti_sub,
        "email": email,
        "name": name,
        "issuer": issuer,
        "client_id": client_id,
    }

    logger.info("lti.launch_success", extra={
        "issuer": issuer,
        "sub": lti_sub,
    })

    # Redirect to app
    return redirect("/")


@lti_bp.route("/jwks")
def lti_jwks():
    """Serve our JWKS for tool-to-platform communication."""
    # In a full implementation, this would serve the tool's public keys
    # For now, return an empty keyset
    return jsonify({"keys": []})
