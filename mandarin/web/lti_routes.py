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

from .api_errors import api_error_handler

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
@api_error_handler("LTI login")
def lti_login():
    """OIDC login initiation (Step 1 of LTI 1.3 launch)."""
    if not _HAS_DEPS:
        return jsonify({"error": "LTI dependencies not installed"}), 501

    try:
        from .. import db
        issuer = request.values.get("iss", "")
        client_id = request.values.get("client_id", "")
        login_hint = request.values.get("login_hint", "")
        target_link_uri = request.values.get("target_link_uri", "")
        lti_message_hint = request.values.get("lti_message_hint", "")

        with db.connection() as conn:
            platform = _get_platform(conn, issuer, client_id)
    except Exception as e:
        logger.error("LTI login initiation failed: %s", e, exc_info=True)
        return jsonify({"error": "LTI login failed"}), 500

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
@api_error_handler("LTI launch")
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
    except Exception as e:
        logger.warning("LTI token decode failed: %s", type(e).__name__)
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
    except Exception as e:
        logger.error("LTI JWKS fetch failed: %s", e)
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

    # Look up existing LTI user mapping or create one
    with db.connection() as conn:
        mapping = conn.execute(
            "SELECT user_id FROM lti_user_mapping WHERE issuer = ? AND lti_sub = ?",
            (issuer, lti_sub)
        ).fetchone()

        if mapping:
            # Existing mapping — log in
            user_id = mapping["user_id"]
        elif email:
            # Try to find user by email
            existing = conn.execute(
                "SELECT id FROM user WHERE email = ? AND is_active = 1", (email,)
            ).fetchone()
            if existing:
                user_id = existing["id"]
                # Create mapping
                conn.execute(
                    "INSERT INTO lti_user_mapping (user_id, issuer, lti_sub) VALUES (?, ?, ?)",
                    (user_id, issuer, lti_sub)
                )
                conn.commit()
            else:
                # Create new user + mapping
                from ..auth import create_user
                import secrets as _sec
                temp_password = _sec.token_urlsafe(24)
                try:
                    user_dict = create_user(conn, email, temp_password, display_name=name)
                    user_id = user_dict["id"]
                    conn.execute(
                        "INSERT INTO lti_user_mapping (user_id, issuer, lti_sub) VALUES (?, ?, ?)",
                        (user_id, issuer, lti_sub)
                    )
                    conn.commit()
                except ValueError:
                    return jsonify({"error": "Could not create account"}), 400
        else:
            return jsonify({"error": "No email provided by LTI platform"}), 400

        # Log in the user via Flask-Login
        from ..auth import get_user_by_id
        user_dict = get_user_by_id(conn, user_id)
        if user_dict:
            from .auth_routes import User
            from flask_login import login_user as _login_user
            _login_user(User(user_dict), remember=False)

    # Store LTI context in session for AGS grade passback
    session["lti_user"] = {
        "sub": lti_sub,
        "email": email,
        "name": name,
        "issuer": issuer,
        "client_id": client_id,
    }

    # Store AGS endpoint if present (for grade passback)
    ags_claim = claims.get("https://purl.imsglobal.org/spec/lti-ags/claim/endpoint", {})
    if ags_claim:
        session["lti_ags"] = {
            "lineitems": ags_claim.get("lineitems", ""),
            "lineitem": ags_claim.get("lineitem", ""),
            "scope": ags_claim.get("scope", []),
        }

    logger.info("lti.launch_success", extra={
        "issuer": issuer,
        "sub": lti_sub,
        "user_id": user_id,
    })

    # Redirect to app
    return redirect("/")


@lti_bp.route("/grade", methods=["POST"])
@api_error_handler("LTI grade")
def lti_grade_passback():
    """Post a grade back to the LTI platform via AGS."""
    if not _HAS_DEPS:
        return jsonify({"error": "LTI dependencies not installed"}), 501

    from flask_login import current_user as _cu
    if not _cu.is_authenticated:
        return jsonify({"error": "Not authenticated"}), 401

    lti_ags = session.get("lti_ags")
    lti_user = session.get("lti_user")
    if not lti_ags or not lti_user:
        return jsonify({"error": "No LTI context"}), 400

    lineitem_url = lti_ags.get("lineitem", "")
    if not lineitem_url:
        return jsonify({"error": "No line item URL for grade passback"}), 400

    data = request.get_json(silent=True) or {}
    score = data.get("score")  # 0.0 - 1.0
    if score is None or not isinstance(score, (int, float)):
        return jsonify({"error": "score (0.0-1.0) required"}), 400
    score = max(0.0, min(1.0, float(score)))

    # Get platform for OAuth2 token
    issuer = lti_user.get("issuer", "")
    client_id_val = lti_user.get("client_id", "")

    from .. import db as _db
    with _db.connection() as conn:
        platform = _get_platform(conn, issuer, client_id_val)

    if not platform:
        return jsonify({"error": "Platform not found"}), 400

    # Obtain OAuth2 access token from platform
    try:
        token_resp = _requests.post(
            platform["token_url"],
            data={
                "grant_type": "client_credentials",
                "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                "client_assertion": _make_client_assertion(platform),
                "scope": "https://purl.imsglobal.org/spec/lti-ags/scope/score",
            },
            timeout=10,
        )
        access_token = token_resp.json().get("access_token")
        if not access_token:
            return jsonify({"error": "Could not obtain access token"}), 502
    except Exception as e:
        logger.error("AGS token error: %s", e)
        return jsonify({"error": "Token request failed"}), 502

    # POST score to line item
    import datetime as _dt
    score_payload = {
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "scoreGiven": score * 100,
        "scoreMaximum": 100,
        "activityProgress": "Completed",
        "gradingProgress": "FullyGraded",
        "userId": lti_user["sub"],
    }

    try:
        scores_url = lineitem_url.rstrip("/") + "/scores"
        resp = _requests.post(
            scores_url,
            json=score_payload,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/vnd.ims.lis.v1.score+json",
            },
            timeout=10,
        )
        if resp.status_code in (200, 201, 204):
            return jsonify({"posted": True, "score": score})
        else:
            logger.error("AGS score post failed: %s %s", resp.status_code, resp.text)
            return jsonify({"error": "Grade passback failed"}), 502
    except Exception as e:
        logger.error("AGS score post error: %s", e)
        return jsonify({"error": "Grade passback request failed"}), 502


def _make_client_assertion(platform):
    """Create a JWT client assertion for OAuth2 token request."""
    import time as _time
    now = int(_time.time())
    payload = {
        "iss": platform["client_id"],
        "sub": platform["client_id"],
        "aud": platform["token_url"],
        "iat": now,
        "exp": now + 300,
        "jti": secrets.token_urlsafe(16),
    }
    # Sign with our tool's private key (if available)
    # For now, use HS256 with client_id as a placeholder
    return pyjwt.encode(payload, platform["client_id"], algorithm="HS256")


@lti_bp.route("/jwks")
@api_error_handler("LTI JWKS")
def lti_jwks():
    """Serve our JWKS for tool-to-platform communication."""
    # In a full implementation, this would serve the tool's public keys
    # For now, return an empty keyset
    return jsonify({"keys": []})
