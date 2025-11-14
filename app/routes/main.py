from flask import Blueprint, render_template, request, session, jsonify
from flask_login import current_user
from app import db

main_bp = Blueprint("main", __name__)

@main_bp.route("/")  # This is the homepage
def home():
    return render_template("index.html")


@main_bp.route("/theme", methods=["POST"])
def update_theme():
    payload = request.get_json(silent=True) or {}
    mode = (payload.get("mode") or "").lower()
    if mode not in {"light", "dark"}:
        return jsonify({"status": "error", "message": "Invalid theme mode."}), 400

    session["theme_mode"] = mode
    if current_user.is_authenticated:
        current_user.theme_mode = mode
        db.session.commit()

    return jsonify({"status": "ok", "mode": mode})
