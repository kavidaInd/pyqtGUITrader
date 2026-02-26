"""
server/server_api_example.py
=============================
Reference Flask server implementation for the Algo Trading SaaS activation system.

Deploy this on any Python hosting (Railway, Heroku, Render, VPS, etc.)

Install:
    pip install flask flask-sqlalchemy

Run (development):
    python server_api_example.py

Production (Gunicorn):
    gunicorn -w 4 -b 0.0.0.0:5000 server_api_example:app

Database:
    SQLite (built-in, no setup) for solo operation.
    Replace DATABASE_URL with PostgreSQL for production scale.

Security checklist before going live:
    [ ] Set SECRET_KEY to a long random value via environment variable
    [ ] Add rate limiting (flask-limiter) to /activate and /verify
    [ ] Enable HTTPS (nginx + certbot)
    [ ] Store order data from your payment provider (Razorpay / Stripe / Gumroad)
    [ ] Add an admin panel to revoke / extend licenses
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Dict, Optional, Tuple

from flask import Flask, jsonify, request, abort
from flask_sqlalchemy import SQLAlchemy

# ── App & DB ───────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///licenses.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", secrets.token_hex(32))

db = SQLAlchemy(app)

# ── Config ────────────────────────────────────────────────────────────────────
LICENSE_DURATION_DAYS: int = 365  # 1-year license
TRIAL_DURATION_DAYS: int = 7  # free trial length in days
MAX_TRIALS_PER_EMAIL: int = 1  # prevent multi-account abuse
MAX_MACHINES_PER_ORDER: int = 1  # 1 machine per order (change for multi-seat)
CURRENT_APP_VERSION: str = "1.0.0"
LATEST_DOWNLOAD_URL: str = os.environ.get(
    "DOWNLOAD_URL", "https://cdn.yourdomain.com/releases/latest/installer.exe"
)


# ── DB Models ─────────────────────────────────────────────────────────────────

class Order(db.Model):
    """
    Created when a customer purchases via your payment provider webhook.
    Gumroad / Razorpay / Stripe → webhook → create_order()
    """
    __tablename__ = "orders"

    id = db.Column(db.String(64), primary_key=True)  # payment provider order id
    email = db.Column(db.String(255), nullable=False, index=True)
    plan = db.Column(db.String(32), default="standard")
    customer_name = db.Column(db.String(255), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_valid = db.Column(db.Boolean, default=True)

    licenses = db.relationship("License", backref="order", lazy=True)


class License(db.Model):
    """One row per activated machine."""
    __tablename__ = "licenses"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    order_id = db.Column(db.String(64), db.ForeignKey("orders.id"), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    license_key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    machine_id = db.Column(db.String(64), nullable=False)
    plan = db.Column(db.String(32), default="standard")
    activated_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    last_verified = db.Column(db.DateTime)
    is_revoked = db.Column(db.Boolean, default=False)
    revoke_reason = db.Column(db.String(255), default="")


class TrialRecord(db.Model):
    """
    One row per machine that has ever started a trial.
    machine_id is stored permanently — reinstalling cannot earn a second trial.
    """
    __tablename__ = "trial_records"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    machine_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    license_key = db.Column(db.String(64), unique=True, nullable=False)
    activated_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    last_verified = db.Column(db.DateTime)
    is_revoked = db.Column(db.Boolean, default=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_license_key() -> str:
    """e.g. AT-A1B2-C3D4-E5F6-G7H8"""
    raw = secrets.token_hex(10).upper()
    parts = [raw[i:i + 4] for i in range(0, 20, 4)]
    return "AT-" + "-".join(parts)


def _error(msg: str, code: int = 400):
    return jsonify({"status": "error", "reason": msg}), code


def _get_json() -> Dict:
    data = request.get_json(silent=True) or {}
    return data


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/api/v1/trial", methods=["POST"])
def start_trial():
    """
    Register a new free trial.

    Body: { email, machine_id, app_version }

    Rules enforced:
      - One trial per machine_id (hardware fingerprint) for all time.
      - MAX_TRIALS_PER_EMAIL trials per email address (soft limit against
        multi-account abuse — adjust as needed).
    """
    data = _get_json()
    email = (data.get("email") or "").strip().lower()
    machine_id = (data.get("machine_id") or "").strip()

    if not email or "@" not in email:
        return _error("invalid_email", 400)
    if not machine_id:
        return _error("machine_id is required.", 400)

    # One trial per machine — permanent, survives reinstall
    existing = TrialRecord.query.filter_by(machine_id=machine_id).first()
    if existing:
        return _error("trial_already_used", 400)

    # Soft per-email limit
    email_trials = TrialRecord.query.filter_by(email=email).count()
    if email_trials >= MAX_TRIALS_PER_EMAIL:
        return _error("trial_already_used", 400)

    expires_at = datetime.utcnow() + timedelta(days=TRIAL_DURATION_DAYS)
    license_key = _generate_license_key()

    trial = TrialRecord(
        machine_id=machine_id,
        email=email,
        license_key=license_key,
        expires_at=expires_at,
    )
    db.session.add(trial)
    db.session.commit()

    days_remaining = (expires_at - datetime.utcnow()).days
    return jsonify({
        "status": "trial_activated",
        "license_key": license_key,
        "expires_at": expires_at.isoformat(),
        "days_remaining": days_remaining,
        "plan": "trial",
    })


@app.route("/api/v1/activate", methods=["POST"])
def activate():
    """
    Activate a license for a machine.

    Body: { order_id, email, machine_id, app_version }
    """
    data = _get_json()
    order_id = (data.get("order_id") or "").strip()
    email = (data.get("email") or "").strip().lower()
    machine_id = (data.get("machine_id") or "").strip()

    if not order_id or not email or not machine_id:
        return _error("order_id, email, and machine_id are required.")

    # Look up order
    order = Order.query.get(order_id)
    if order is None:
        return _error("Order not found. Check your Order ID.")

    if not order.is_valid:
        return _error("This order has been cancelled or refunded.")

    if order.email.lower() != email:
        return _error("Email does not match the order. Check your email.")

    # Check machine count
    existing_licenses = License.query.filter_by(
        order_id=order_id, is_revoked=False
    ).all()

    # Check if this exact machine is already activated
    for lic in existing_licenses:
        if lic.machine_id == machine_id:
            # Re-activation of same machine — return existing key
            return jsonify({
                "status": "activated",
                "license_key": lic.license_key,
                "expires_at": lic.expires_at.isoformat(),
                "plan": lic.plan,
                "customer_name": order.customer_name,
            })

    if len(existing_licenses) >= MAX_MACHINES_PER_ORDER:
        return _error(
            f"This order already has {MAX_MACHINES_PER_ORDER} machine(s) activated. "
            "Contact support to transfer your license."
        )

    # Create new license
    expires_at = datetime.utcnow() + timedelta(days=LICENSE_DURATION_DAYS)
    license_key = _generate_license_key()

    lic = License(
        order_id=order_id,
        email=email,
        license_key=license_key,
        machine_id=machine_id,
        plan=order.plan,
        expires_at=expires_at,
    )
    db.session.add(lic)
    db.session.commit()

    return jsonify({
        "status": "activated",
        "license_key": license_key,
        "expires_at": expires_at.isoformat(),
        "plan": order.plan,
        "customer_name": order.customer_name,
    })


@app.route("/api/v1/verify", methods=["POST"])
def verify():
    """
    Verify a license key on each app start.

    Body: { license_key, machine_id, app_version }
    """
    data = _get_json()
    license_key = (data.get("license_key") or "").strip()
    machine_id = (data.get("machine_id") or "").strip()

    if not license_key or not machine_id:
        return jsonify({"valid": False, "reason": "missing_fields"})

    # ── Check trial records first ─────────────────────────────────────────
    trial = TrialRecord.query.filter_by(license_key=license_key).first()
    if trial:
        if trial.is_revoked:
            return jsonify({"valid": False, "reason": "revoked"})
        if trial.machine_id != machine_id:
            return jsonify({"valid": False, "reason": "invalid_machine"})
        if datetime.utcnow() > trial.expires_at:
            return jsonify({"valid": False, "reason": "trial_expired"})
        trial.last_verified = datetime.utcnow()
        db.session.commit()
        days_remaining = max(0, (trial.expires_at - datetime.utcnow()).days)
        return jsonify({
            "valid": True,
            "plan": "trial",
            "expires_at": trial.expires_at.isoformat(),
            "days_remaining": days_remaining,
            "customer_name": trial.email,
        })

    # ── Check paid licenses ───────────────────────────────────────────────
    lic = License.query.filter_by(license_key=license_key).first()

    if lic is None:
        return jsonify({"valid": False, "reason": "invalid_key"})

    if lic.is_revoked:
        return jsonify({"valid": False, "reason": lic.revoke_reason or "revoked"})

    if lic.machine_id != machine_id:
        return jsonify({"valid": False, "reason": "invalid_machine"})

    if datetime.utcnow() > lic.expires_at:
        return jsonify({"valid": False, "reason": "expired"})

    # Check parent order is still valid
    if not lic.order.is_valid:
        return jsonify({"valid": False, "reason": "order_cancelled"})

    # Update heartbeat
    lic.last_verified = datetime.utcnow()
    db.session.commit()
    days_remaining = max(0, (lic.expires_at - datetime.utcnow()).days)

    return jsonify({
        "valid": True,
        "expires_at": lic.expires_at.isoformat(),
        "plan": lic.plan,
        "days_remaining": days_remaining,
        "customer_name": lic.order.customer_name,
    })


@app.route("/api/v1/version", methods=["GET"])
def version():
    """
    Return latest version info. Queried on each app start for auto-update.
    Customise LATEST_VERSION and DOWNLOAD_URL per platform.
    """
    requested_platform = request.args.get("platform", "windows")

    platform_urls = {
        "windows": os.environ.get("DOWNLOAD_URL_WIN", LATEST_DOWNLOAD_URL),
        "macos": os.environ.get("DOWNLOAD_URL_MAC", LATEST_DOWNLOAD_URL),
        "linux": os.environ.get("DOWNLOAD_URL_LIN", LATEST_DOWNLOAD_URL),
    }
    download_url = platform_urls.get(requested_platform, LATEST_DOWNLOAD_URL)

    latest_version = os.environ.get("LATEST_VERSION", CURRENT_APP_VERSION)
    is_mandatory = os.environ.get("UPDATE_MANDATORY", "false").lower() == "true"
    min_version = os.environ.get("MIN_VERSION", "1.0.0")
    release_notes = os.environ.get("RELEASE_NOTES", "")
    checksum = os.environ.get("CHECKSUM_SHA256", "")

    return jsonify({
        "latest_version": latest_version,
        "download_url": download_url,
        "release_notes": release_notes,
        "is_mandatory": is_mandatory,
        "min_version": min_version,
        "checksum_sha256": checksum,
    })


# ── Admin helpers (protect these with basic auth in production) ───────────────

@app.route("/admin/create_order", methods=["POST"])
def admin_create_order():
    """
    Called by your payment webhook (Gumroad / Razorpay / Stripe) to register
    a new purchase.  Protect with an admin API key in production.

    Body: { order_id, email, customer_name, plan }
    """
    # ── Basic security: require admin key in header ──────────────────────────
    admin_key = os.environ.get("ADMIN_KEY", "change-me-in-production")
    if request.headers.get("X-Admin-Key") != admin_key:
        abort(401)

    data = _get_json()
    oid = (data.get("order_id") or "").strip()
    email = (data.get("email") or "").strip().lower()
    name = (data.get("customer_name") or "").strip()
    plan = (data.get("plan") or "standard").strip()

    if not oid or not email:
        return _error("order_id and email are required.")

    if Order.query.get(oid):
        return _error("Order already exists.")

    order = Order(id=oid, email=email, customer_name=name, plan=plan)
    db.session.add(order)
    db.session.commit()

    return jsonify({"status": "created", "order_id": oid})


@app.route("/admin/revoke_license", methods=["POST"])
def admin_revoke():
    """Revoke a specific license key."""
    admin_key = os.environ.get("ADMIN_KEY", "change-me-in-production")
    if request.headers.get("X-Admin-Key") != admin_key:
        abort(401)

    data = _get_json()
    license_key = (data.get("license_key") or "").strip()
    reason = (data.get("reason") or "revoked_by_admin").strip()

    lic = License.query.filter_by(license_key=license_key).first()
    if not lic:
        return _error("License not found.")

    lic.is_revoked = True
    lic.revoke_reason = reason
    db.session.commit()

    return jsonify({"status": "revoked"})


@app.route("/admin/revoke_trial", methods=["POST"])
def admin_revoke_trial():
    """Revoke a trial license (e.g. abuse detection)."""
    admin_key = os.environ.get("ADMIN_KEY", "change-me-in-production")
    if request.headers.get("X-Admin-Key") != admin_key:
        abort(401)
    data = _get_json()
    machine_id = (data.get("machine_id") or "").strip()
    trial = TrialRecord.query.filter_by(machine_id=machine_id).first()
    if not trial:
        return _error("Trial record not found.")
    trial.is_revoked = True
    db.session.commit()
    return jsonify({"status": "revoked"})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        print("Database tables created.")
        print("Starting development server on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
