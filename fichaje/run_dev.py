"""Lanzador exclusivo del entorno local de desarrollo."""

import os


HOST = "127.0.0.1"
PORT = 5020
DATABASE = "fichaje_dev"
USER = "fichaje_dev"


def load_local_secrets():
    for name in ('FICHAJE_DEV_DB_PASSWORD', 'FICHAJE_DEV_SECRET_KEY'):
        if not os.environ.get(name):
            raise RuntimeError(f'Missing {name}; configure the development environment.')


def verify_local_connection(app, db):
    from sqlalchemy import text
    from config.development_config import validate_development_database_uri

    parsed = validate_development_database_uri(
        app.config["SQLALCHEMY_DATABASE_URI"]
    )
    if parsed.username != USER:
        raise RuntimeError("Refusing to serve with a non-development user.")

    with app.app_context():
        row = db.session.execute(
            text("SELECT DATABASE(), @@port")
        ).one()
        database, port = row
        if database != parsed.database or int(port) != parsed.port:
            raise RuntimeError("Refusing to serve a non-development database.")


def main():
    os.environ.pop("FICHAJE_TESTING", None)
    os.environ["FICHAJE_ENV"] = "development"
    load_local_secrets()

    from app import app, db

    verify_local_connection(app, db)
    print("ENTORNO DE DESARROLLO — BASE LOCAL")
    app.run(host=HOST, port=PORT, debug=False)


if __name__ == "__main__":
    main()
