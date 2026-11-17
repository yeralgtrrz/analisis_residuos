from flask import Flask

from .routes.api import api
from .routes.pages import pages


def create_app():
    app = Flask(__name__)
    app.register_blueprint(pages)
    app.register_blueprint(api, url_prefix="/api")
    return app
