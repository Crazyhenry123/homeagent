from flask import Flask
from flask_cors import CORS

from app.config import Config
from app.models.dynamo import init_tables
from app.routes.health import health_bp
from app.routes.auth_routes import admin_bp, auth_bp
from app.routes.chat import chat_bp
from app.routes.conversations import conversations_bp


def create_app(config: Config | None = None) -> Flask:
    app = Flask(__name__)

    if config is None:
        config = Config()
    app.config.from_object(config)
    CORS(app)

    init_tables(app)

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(chat_bp, url_prefix="/api")
    app.register_blueprint(conversations_bp, url_prefix="/api")

    return app
