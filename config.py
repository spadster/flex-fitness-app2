import os

basedir = os.path.abspath(os.path.dirname(__file__))
# eref jnyh bfcz zwpu
class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev_secret_key"

    # Database file stored inside the project folder
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or \
        "sqlite:///" + os.path.join(basedir, "db.sqlite3")

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Mail settings (used for email verification). Configure via environment variables.
    MAIL_SERVER = os.environ.get("MAIL_SERVER") or "smtp.gmail.com"
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME") or "awank6107@gmail.com"
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD") or "eref jnyh bfcz zwpu"
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "True") == "True"
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "False") == "True"
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER") or "Fitness Application"

    # Base URL used to build verification links (adjust for production)
    APP_BASE_URL = os.environ.get("APP_BASE_URL") or "http://127.0.0.1:5000"
