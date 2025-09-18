from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import config.config as cfg

app = Flask(__name__)
app.config.from_object(cfg)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

from app import routes, models