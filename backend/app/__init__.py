from flask import Flask
from flask_cors import CORS

from app.config import Config
from app.models.dynamo import init_tables
from app.routes.agent_config_routes import agent_config_bp
from app.routes.agent_template_routes import agent_template_bp
from app.routes.health import health_bp
from app.routes.auth_routes import admin_bp, auth_bp
from app.routes.chat import chat_bp
from app.routes.conversations import conversations_bp
from app.routes.family_tree import family_tree_bp
from app.routes.health_records import admin_health_records_bp, health_records_bp
from app.routes.health_reports import health_reports_bp
from app.routes.health_documents import admin_health_documents_bp
from app.routes.member_agent_routes import member_agent_bp
from app.routes.profiles import admin_profiles_bp, profiles_bp
from app.services.agent_management import AgentManagementClient
from app.services.agent_template import seed_builtin_templates


def _seed_agentcore_templates(app: Flask) -> None:
    """Seed built-in templates via the AgentManagementClient."""
    region = app.config["AWS_REGION"]
    endpoint_url = app.config.get("DYNAMODB_ENDPOINT")
    client = AgentManagementClient(region=region, endpoint_url=endpoint_url)
    client.seed_builtin_templates()


def create_app(config: Config | None = None) -> Flask:
    app = Flask(__name__)

    if config is None:
        config = Config()
    app.config.from_object(config)
    CORS(app)

    init_tables(app)
    seed_builtin_templates(app)
    _seed_agentcore_templates(app)

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(chat_bp, url_prefix="/api")
    app.register_blueprint(conversations_bp, url_prefix="/api")
    app.register_blueprint(profiles_bp, url_prefix="/api")
    app.register_blueprint(admin_profiles_bp, url_prefix="/api/admin")
    app.register_blueprint(agent_config_bp, url_prefix="/api/admin")
    app.register_blueprint(agent_template_bp, url_prefix="/api/admin")
    app.register_blueprint(member_agent_bp, url_prefix="/api")
    app.register_blueprint(family_tree_bp, url_prefix="/api/admin")
    app.register_blueprint(health_records_bp, url_prefix="/api")
    app.register_blueprint(admin_health_records_bp, url_prefix="/api/admin")
    app.register_blueprint(health_reports_bp, url_prefix="/api/admin")
    app.register_blueprint(admin_health_documents_bp, url_prefix="/api/admin")

    return app
