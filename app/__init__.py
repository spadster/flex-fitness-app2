from flask import Flask, session
from flask_sqlalchemy import SQLAlchemy 
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user


db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login_trainer"
    login_manager.login_message_category = "warning"

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id: str):
        if user_id is None:
            return None
        return User.query.get(int(user_id))

    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.trainer import trainer_bp
    from app.routes.member import member_bp
    from app.routes.template import template_bp

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(trainer_bp)
    app.register_blueprint(member_bp)
    app.register_blueprint(template_bp)

    @app.context_processor
    def inject_theme_mode():
        mode = session.get("theme_mode")
        if current_user.is_authenticated and getattr(current_user, "theme_mode", None):
            mode = current_user.theme_mode
        if not mode:
            mode = "light"
        session["theme_mode"] = mode
        return {"theme_mode": mode}

    return app
