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
        email = request.form["email"]
        password = request.form["password"]
        user = User.query.filter_by(email=email, role="trainer").first()
        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            session["role"] = user.role
            # Render the dashboard template
            return render_template("dashboard-trainer.html", user=user)
        flash("Invalid email or password")
    return render_template("login-trainer.html")


# Trainee login
@auth_bp.route("/login-member", methods=["GET", "POST"])
def login_member():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            session["role"] = user.role
            return render_template("dashboard-member.html")
        flash("Invalid email or password")
    return render_template("login-member.html")

# Create an account
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        first_name = request.form["first_name"]
        last_name = request.form["last_name"]
        email = request.form["email"]
        password_hash = generate_password_hash(request.form["password"])
        role = request.form["role"]

        # Check for existing user
        if User.query.filter_by(email=email).first():
            flash("Email already registered. Please log in.")
            return redirect(url_for("auth.register"))

        user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            password_hash=password_hash,
            role=role
        )
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