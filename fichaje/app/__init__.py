import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate

app = Flask(__name__)

if os.environ.get("FICHAJE_TESTING") == "1":
    from config.test_config import TestConfig, assert_safe_test_database_uri

    app.config.from_object(TestConfig)
    assert_safe_test_database_uri(app.config["SQLALCHEMY_DATABASE_URI"])
    app.config["FICHAJE_ENV"] = "test"
elif os.environ.get("FICHAJE_ENV") == "development":
    from config.development_config import load_development_config

    app.config.from_mapping(load_development_config())
elif os.environ.get("FICHAJE_ENV") == "production":
    import config.config as cfg

    app.config.from_object(cfg)
    app.config["FICHAJE_ENV"] = "production"
else:
    raise RuntimeError(
        "FICHAJE_ENV must be explicitly set to development "
        "or production."
    )

app.config.setdefault("ALLOW_EMAILS", False)
app.config.setdefault("ALLOW_DISCORD", False)
app.config.setdefault("ALLOW_PUSH", False)
app.config.setdefault("ALLOW_AUTOFICHAJE", False)
app.config.setdefault("DEVELOPMENT_BANNER", "")

from app.services.csrf import init_csrf

init_csrf(app)

db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = "login"

from app import routes, models
