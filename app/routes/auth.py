from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models import User  # import models here, not __init__.py

# Define the blueprint at the top level
auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

# Trainer login
@auth_bp.route("/login-trainer", methods=["GET", "POST"])
def login_trainer():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        user = User.query.filter_by(email=email, role="trainer").first()
        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            session["role"] = user.role
            return redirect(url_for("trainer.dashboard_trainer"))
        flash("Invalid email or password")
    return render_template("login-trainer.html")


# Member login
@auth_bp.route("/login-member", methods=["GET", "POST"])
def login_member():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            session["role"] = user.role
            return redirect(url_for("member.dashboard"))
        flash("Invalid email or password")
    return render_template("login-member.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        first_name = request.form["first_name"]
        last_name = request.form["last_name"]
        email = request.form["email"]
        password = request.form["password"]
        role = request.form["role"]

        # Enforce minimum password length
        if len(password) < 8:
            flash("Password must be at least 8 characters long.")
            return redirect(url_for("auth.register"))

        # Check for existing user
        if User.query.filter_by(email=email).first():
            flash("Email already registered. Please log in.")
            return redirect(url_for("auth.register"))

        # Hash password *after* validation
        password_hash = generate_password_hash(password)

        user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            password_hash=password_hash,
            role=role
        )

        if user.role == 'trainer':
            user.generate_trainer_code()

        db.session.add(user)
        db.session.commit()

        flash("Account created successfully!")
        return redirect(url_for("auth.login_trainer" if role == "trainer" else "auth.login_member"))

    return render_template("create-account.html")


# Logout
@auth_bp.route("/logout")
def logout():
    session.clear()  # removes all session data
    flash("You have been logged out.")
    return redirect(url_for("main.home"))  # redirect to homepage