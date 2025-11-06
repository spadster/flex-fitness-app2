#!/usr/bin/env python3
"""Simple SMTP tester that uses the app's MAIL_* environment variables.

Usage:
  - Set MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD, MAIL_USE_TLS (True/False),
    MAIL_USE_SSL (True/False), MAIL_DEFAULT_SENDER, and RECIPIENT (optional).
  - Then run: python3 scripts/test_smtp.py

By default RECIPIENT falls back to MAIL_USERNAME.
"""
import os
import sys
import ssl
import smtplib
from email.message import EmailMessage

# Ensure project root is on sys.path so we can import config.py from repo root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Read settings from config.Config so this script uses the same config as the app
from config import Config
cfg = Config()


def main():
    # Remove HTTP(S)_PROXY/ALL_PROXY from environment for this test to avoid proxy interference
    for proxy_var in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        os.environ.pop(proxy_var, None)

    mail_server = cfg.MAIL_SERVER
    if not mail_server:
        print("MAIL_SERVER is not set (check your environment variables or config.py). Set environment variables first.")
        sys.exit(2)

    port = cfg.MAIL_PORT
    username = cfg.MAIL_USERNAME
    password = cfg.MAIL_PASSWORD
    use_tls = cfg.MAIL_USE_TLS
    use_ssl = cfg.MAIL_USE_SSL
    sender = cfg.MAIL_DEFAULT_SENDER or username
    # allow overriding recipient with env var RECIPIENT for testing convenience
    recipient = os.environ.get("RECIPIENT") or username

    msg = EmailMessage()
    msg.set_content("This is a test email from flex-fitness-app.")
    msg["Subject"] = "Flex Fitness SMTP test"
    msg["From"] = sender
    msg["To"] = recipient

    print(f"Trying to send test email via {mail_server}:{port} (ssl={use_ssl}, tls={use_tls})")

    try:
        if use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(mail_server, port, context=context) as server:
                if username and password:
                    server.login(username, password)
                server.send_message(msg)
        else:
            # Use an explicit SSL context with starttls for better compatibility
            context = ssl.create_default_context()
            with smtplib.SMTP(mail_server, port, timeout=30) as server:
                server.set_debuglevel(1)
                server.ehlo()
                if use_tls:
                    try:
                        server.starttls(context=context)
                        server.ehlo()
                    except Exception as starttls_exc:
                        # If STARTTLS fails, show the underlying error and attempt SSL on 465 as a fallback
                        print("STARTTLS failed:", repr(starttls_exc))
                        if port != 465:
                            print("Attempting fallback to SSL on port 465...")
                            try:
                                with smtplib.SMTP_SSL(mail_server, 465, context=context) as ssl_server:
                                    ssl_server.set_debuglevel(1)
                                    if username and password:
                                        ssl_server.login(username, password)
                                    ssl_server.send_message(msg)
                                print("Fallback SSL send succeeded (port 465).")
                                return
                            except Exception as ssl_exc:
                                print("Fallback SSL also failed:", repr(ssl_exc))
                                raise
                        else:
                            raise
                if username and password:
                    server.login(username, password)
                server.send_message(msg)

    except Exception as e:
        print("Failed to send test email:", repr(e))
        sys.exit(1)

    print(f"Test email sent to {recipient} (or accepted by SMTP server).")


if __name__ == "__main__":
    main()
