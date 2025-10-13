from flask import Flask
from flask_sqlalchemy import SQLAlchemy 
from flask_migrate import Migrate


db = SQLAlchemy()
migrate = Migrate()

def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)

    from app.routes.auth import auth_bp
    from app.routes.main import main_bp

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    return app
