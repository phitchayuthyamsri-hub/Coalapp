from flask import Flask
from flask_login import LoginManager

from config import Config
from .models import db, User

login_manager = LoginManager()
login_manager.login_view = "auth.login"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)

    from .auth import bp as auth_bp
    from .views import bp as views_bp
    from .api import bp as api_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp)

    with app.app_context():
        db.create_all()
        from .seed import seed_if_empty
        seed_if_empty()

    return app
