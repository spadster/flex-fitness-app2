from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models import User
import secrets
from datetime import datetime, timedelta
import smtplib, ssl
from email.message import EmailMessage

# Define the blueprint at the top level
auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


# -----------------------------
# Trainer Login
# -----------------------------
@auth_bp.route("/login-trainer", methods=["GET", "POST"])
def login_trainer():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        user = User.query.filter_by(email=email, role="trainer").first()

        if not user or not check_password_hash(user.password_hash, password):
            flash("Email or password incorrect.", "danger")
            return redirect(url_for("auth.login_trainer"))

        if not getattr(user, "email_verified", False):
            flash("Please verify your email before logging in. Check your inbox (or spam).", "warning")
            return redirect(url_for("auth.login_trainer"))

        login_user(user)
        session["user_id"] = user.id
        session["role"] = user.role
        session["theme_mode"] = user.theme_mode or session.get("theme_mode") or "light"
        flash(f"Welcome, Trainer {user.first_name}!", "success")
        return redirect(url_for("trainer.dashboard_trainer"))

    return render_template("login-trainer.html")


# -----------------------------
# Member Login
# -----------------------------
@auth_bp.route("/login-member", methods=["GET", "POST"])
def login_member():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password_hash, password):
            flash("Email or password incorrect.", "danger")
            return redirect(url_for("auth.login_member"))

        if not getattr(user, "email_verified", False):
            flash("Please verify your email before logging in. Check your inbox (or spam).", "warning")
            return redirect(url_for("auth.login_member"))

        login_user(user)
        session["user_id"] = user.id
        session["role"] = user.role
        session["theme_mode"] = user.theme_mode or session.get("theme_mode") or "light"
        flash(f"Welcome back, {user.first_name}!", "success")

        if user.role == "trainer":
            return redirect(url_for("trainer.dashboard_trainer"))
        return redirect(url_for("member.dashboard"))

    return render_template("login-member.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # DEBUG: Print config to console
        print("\n" + "="*50)
        print("EMAIL CONFIGURATION CHECK")
        print("="*50)
        print(f"MAIL_SERVER: {current_app.config.get('MAIL_SERVER')}")
        print(f"MAIL_PORT: {current_app.config.get('MAIL_PORT')}")
        print(f"MAIL_USERNAME: {current_app.config.get('MAIL_USERNAME')}")
        print(f"MAIL_PASSWORD exists: {bool(current_app.config.get('MAIL_PASSWORD'))}")
        print(f"MAIL_DEFAULT_SENDER: {current_app.config.get('MAIL_DEFAULT_SENDER')}")
        print(f"APP_BASE_URL: {current_app.config.get('APP_BASE_URL')}")
        print(f"Debug mode: {current_app.debug}")
        print("="*50 + "\n")
        
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        role = request.form.get("role", "").strip()

        current_app.logger.info("Register called: first_name=%s last_name=%s email=%s role=%s", 
                               first_name, last_name, email, role)

        # Enforce minimum password length
        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "warning")
            return redirect(url_for("auth.register"))

        if password != confirm_password:
            flash("Passwords do not match. Please try again.", "warning")
            return redirect(url_for("auth.register"))

        # Check for existing user
        if User.query.filter_by(email=email).first():
            flash("Email already registered. Please log in.", "warning")
            return redirect(url_for("auth.register"))

        # Hash password
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

        # Generate verification token and timestamp
        token = secrets.token_urlsafe(32)
        user.email_verification_token = token
        user.email_verification_sent_at = datetime.utcnow()

        try:
            db.session.add(user)
            db.session.commit()
            current_app.logger.info("User created: id=%s email=%s", user.id, user.email)
        except Exception as db_exc:
            current_app.logger.exception("Database error creating user: %s", db_exc)
            flash("An error occurred while creating your account. Please try again.", "danger")
            return redirect(url_for("auth.register"))

        # Build verification link
        base = current_app.config.get("APP_BASE_URL", "http://localhost:5000")
        verify_link = f"{base.rstrip('/')}/auth/verify-email/{user.email_verification_token}"

        # Send verification email
        email_sent = False
        error_message = None
        
        try:
            print(f"\n>>> Attempting to send verification email to {user.email}")
            current_app.logger.info("Attempting to send verification email to %s", user.email)
            _send_verification_email(user)
            email_sent = True
            print(f">>> Email sent successfully to {user.email}\n")
            current_app.logger.info("Verification email sent successfully to %s", user.email)
        except Exception as e:
            error_message = str(e)
            print(f"\n!!! EMAIL SEND FAILED !!!")
            print(f"!!! Error: {type(e).__name__}: {e}")
            print(f"!!! Verification link: {verify_link}\n")
            current_app.logger.exception("Failed to send verification email: %s", e)

        verify_flash = "Account created! Please verify your email before logging in."

        # Show appropriate message to user
        if not current_app.config.get("MAIL_SERVER"):
            # No email configured - show dev link
            print(f"\n*** DEV MODE: No MAIL_SERVER configured ***")
            print(f"*** Verification link: {verify_link} ***\n")
            flash(f"{verify_flash} No email server configured. Use this link to verify: {verify_link}", "info")
        elif email_sent:
            # Email sent successfully
            flash(f"{verify_flash} We've emailed a verification link to {user.email}.", "success")
        else:
            # Email failed to send
            if current_app.debug:
                flash(f"{verify_flash} Email delivery failed: {error_message}. Verification link: {verify_link}", "warning")
            else:
                flash(f"{verify_flash} We couldn't send the verification email. Please contact support.", "warning")
                print(f"Verification link for support: {verify_link}")

        return redirect(url_for("auth.login_trainer" if role == "trainer" else "auth.login_member"))

    return render_template("create-account.html")


def _send_verification_email(user):
    """Construct and send a verification email to the user using SMTP settings from app config."""
    cfg = current_app.config
    token = user.email_verification_token
    if not token:
        raise RuntimeError("No verification token for user")

    base = cfg.get("APP_BASE_URL", "http://localhost:5000")
    verify_path = f"/auth/verify-email/{token}"
    verify_url = f"{base.rstrip('/')}{verify_path}"

    subject = "Verify your Flex Fitness account"
    body = f"""Hi {user.first_name},

Please verify your email address by clicking the link below:

{verify_url}

This link will expire in 48 hours.

If you didn't create an account, you can ignore this message.

Thanks,
Flex Fitness Team"""

    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = cfg.get("MAIL_DEFAULT_SENDER", cfg.get("MAIL_USERNAME"))
    msg["To"] = user.email

    mail_server = cfg.get("MAIL_SERVER")
    if not mail_server:
        raise RuntimeError("MAIL_SERVER not configured in app config")

    port = cfg.get("MAIL_PORT", 587)
    username = cfg.get("MAIL_USERNAME")
    password = cfg.get("MAIL_PASSWORD")
    use_tls = cfg.get("MAIL_USE_TLS", True)
    use_ssl = cfg.get("MAIL_USE_SSL", False)

    if not username or not password:
        raise RuntimeError("MAIL_USERNAME and MAIL_PASSWORD must be configured")

    print(f"\nSMTP Connection Details:")
    print(f"  Server: {mail_server}:{port}")
    print(f"  Username: {username}")
    print(f"  Use TLS: {use_tls}")
    print(f"  Use SSL: {use_ssl}")

    context = ssl.create_default_context()

    try:
        if use_ssl:
            print(f"  Connecting with SSL...")
            with smtplib.SMTP_SSL(mail_server, port, context=context, timeout=10) as server:
                server.set_debuglevel(1)
                server.login(username, password)
                server.send_message(msg)
                print(f"  ✓ Email sent successfully via SSL")
        else:
            print(f"  Connecting with SMTP...")
            with smtplib.SMTP(mail_server, port, timeout=10) as server:
                server.set_debuglevel(1)
                server.ehlo()
                if use_tls:
                    print(f"  Starting TLS...")
                    server.starttls(context=context)
                    server.ehlo()
                server.login(username, password)
                server.send_message(msg)
                print(f"  ✓ Email sent successfully via SMTP+TLS")
    except smtplib.SMTPAuthenticationError as e:
        raise RuntimeError(f"SMTP Authentication failed. Check your username/password. Error: {e}")
    except smtplib.SMTPException as e:
        raise RuntimeError(f"SMTP error: {e}")
    except Exception as e:
        raise RuntimeError(f"Failed to send email: {type(e).__name__}: {e}")


def _send_password_reset_email(user):
    """Send a password reset email using the configured SMTP settings."""
    cfg = current_app.config
    token = user.password_reset_token
    if not token:
        raise RuntimeError("No password reset token for user")

    base = cfg.get("APP_BASE_URL", "http://localhost:5000")
    reset_path = f"/auth/reset-password/{token}"
    reset_url = f"{base.rstrip('/')}{reset_path}"

    subject = "Reset your Flex Fitness password"
    body = f"""Hi {user.first_name},

You requested a password reset for your Flex Fitness account.
Click the link below to choose a new password:

{reset_url}

This link will expire in 2 hours. If you didn't request a password reset, you can ignore this email.

Thanks,
Flex Fitness Team"""

    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = cfg.get("MAIL_DEFAULT_SENDER", cfg.get("MAIL_USERNAME"))
    msg["To"] = user.email

    mail_server = cfg.get("MAIL_SERVER")
    if not mail_server:
        raise RuntimeError("MAIL_SERVER not configured in app config")

    port = cfg.get("MAIL_PORT", 587)
    username = cfg.get("MAIL_USERNAME")
    password = cfg.get("MAIL_PASSWORD")
    use_tls = cfg.get("MAIL_USE_TLS", True)
    use_ssl = cfg.get("MAIL_USE_SSL", False)

    if not username or not password:
        raise RuntimeError("MAIL_USERNAME and MAIL_PASSWORD must be configured")

    print(f"\nSMTP Connection Details (password reset):")
    print(f"  Server: {mail_server}:{port}")
    print(f"  Username: {username}")
    print(f"  Use TLS: {use_tls}")
    print(f"  Use SSL: {use_ssl}")

    context = ssl.create_default_context()

    try:
        if use_ssl:
            print("  Connecting with SSL...")
            with smtplib.SMTP_SSL(mail_server, port, context=context, timeout=10) as server:
                server.set_debuglevel(1)
                server.login(username, password)
                server.send_message(msg)
                print("  ✓ Password reset email sent successfully via SSL")
        else:
            print("  Connecting with SMTP...")
            with smtplib.SMTP(mail_server, port, timeout=10) as server:
                server.set_debuglevel(1)
                server.ehlo()
                if use_tls:
                    print("  Starting TLS...")
                    server.starttls(context=context)
                    server.ehlo()
                server.login(username, password)
                server.send_message(msg)
                print("  ✓ Password reset email sent successfully via SMTP+TLS")
    except smtplib.SMTPAuthenticationError as e:
        raise RuntimeError(f"SMTP Authentication failed. Check your username/password. Error: {e}")
    except smtplib.SMTPException as e:
        raise RuntimeError(f"SMTP error: {e}")
    except Exception as e:
        raise RuntimeError(f"Failed to send password reset email: {type(e).__name__}: {e}")


@auth_bp.route("/verify-email/<token>")
def verify_email(token):
    user = User.query.filter_by(email_verification_token=token).first()
    if not user:
        flash("Invalid or expired verification link.", "danger")
        return redirect(url_for("main.home"))

    # Optional expiry check: 48 hours
    sent_at = user.email_verification_sent_at
    if sent_at and datetime.utcnow() - sent_at > timedelta(hours=48):
        flash("Verification link has expired. Please request a new verification email.", "warning")
        return redirect(url_for("main.home"))

    user.email_verified = True
    user.email_verification_token = None
    user.email_verification_sent_at = None
    db.session.commit()

    flash("Your email has been verified. You can now log in.", "success")
    
    # Redirect based on user role
    if user.role == "trainer":
        return redirect(url_for("auth.login_trainer"))
    return redirect(url_for("auth.login_member"))


@auth_bp.route("/resend-verification", methods=["GET", "POST"])
def resend_verification():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        if not email:
            flash("Please enter the email associated with your account.", "warning")
            return redirect(url_for("auth.resend_verification"))

        user = User.query.filter_by(email=email).first()
        generic_message = "If we find an account with that email, you'll receive a verification link shortly."

        if not user:
            flash(generic_message, "info")
            return redirect(url_for("auth.resend_verification"))

        if user.email_verified:
            flash("That email is already verified. You can sign in now.", "info")
            return redirect(url_for("auth.login_member"))

        token = secrets.token_urlsafe(32)
        user.email_verification_token = token
        user.email_verification_sent_at = datetime.utcnow()
        db.session.commit()

        base = current_app.config.get("APP_BASE_URL", "http://localhost:5000")
        verify_link = f"{base.rstrip('/')}/auth/verify-email/{token}"

        try:
            _send_verification_email(user)
            flash(generic_message, "info")
        except Exception as e:
            current_app.logger.exception("Failed to resend verification email")
            if not current_app.config.get("MAIL_SERVER"):
                flash(f"{generic_message} No email server configured. Use this link to verify: {verify_link}", "info")
            elif current_app.debug:
                flash(f"{generic_message} Email delivery failed: {e}. Verification link: {verify_link}", "warning")
            else:
                flash("We couldn't send a verification email right now. Please contact support.", "danger")

        return redirect(url_for("auth.resend_verification"))

    return render_template("resend-verification.html")


@auth_bp.route("/password-reset", methods=["GET", "POST"])
def request_password_reset():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        if not email:
            flash("Please enter the email associated with your account.", "warning")
            return redirect(url_for("auth.request_password_reset"))

        user = User.query.filter_by(email=email).first()
        generic_message = "If an account exists for that email, you'll receive a password reset link shortly."

        if not user:
            flash(generic_message, "info")
            return redirect(url_for("auth.request_password_reset"))

        token = secrets.token_urlsafe(32)
        user.password_reset_token = token
        user.password_reset_sent_at = datetime.utcnow()
        db.session.commit()

        base = current_app.config.get("APP_BASE_URL", "http://localhost:5000")
        reset_link = f"{base.rstrip('/')}/auth/reset-password/{token}"

        try:
            _send_password_reset_email(user)
            flash(generic_message, "info")
        except Exception as e:
            current_app.logger.exception("Failed to send password reset email: %s", e)
            if not current_app.config.get("MAIL_SERVER"):
                flash(f"{generic_message} No email server configured. Use this link to reset: {reset_link}", "info")
            elif current_app.debug:
                flash(f"{generic_message} Email delivery failed: {e}. Reset link: {reset_link}", "warning")
            else:
                flash("We couldn't send a reset email right now. Please contact support.", "danger")

        return redirect(url_for("auth.request_password_reset"))

    return render_template("password-reset-request.html")


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = User.query.filter_by(password_reset_token=token).first()
    if not user:
        flash("Invalid or expired password reset link.", "danger")
        return redirect(url_for("auth.request_password_reset"))

    sent_at = user.password_reset_sent_at
    if sent_at and datetime.utcnow() - sent_at > timedelta(hours=2):
        user.password_reset_token = None
        user.password_reset_sent_at = None
        db.session.commit()
        flash("Password reset link has expired. Please request a new one.", "warning")
        return redirect(url_for("auth.request_password_reset"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "warning")
            return redirect(url_for("auth.reset_password", token=token))

        if password != confirm_password:
            flash("Passwords do not match. Please try again.", "warning")
            return redirect(url_for("auth.reset_password", token=token))

        user.password_hash = generate_password_hash(password)
        user.password_reset_token = None
        user.password_reset_sent_at = None
        db.session.commit()

        flash("Password updated. You can now log in.", "success")
        return redirect(url_for("auth.login_member"))

    return render_template("password-reset.html", token=token)


@auth_bp.route("/logout")
def logout():
    theme_pref = getattr(current_user, "theme_mode", None)
    logout_user()
    preserved_theme = theme_pref or session.get("theme_mode") or "light"
    session.clear()
    session["theme_mode"] = preserved_theme
    flash("You have been logged out.", "info")
    return redirect(url_for("main.home"))
