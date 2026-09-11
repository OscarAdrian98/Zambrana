"""Guardas para impedir integraciones accidentales fuera de producción."""


def require_integration(app, config_key, integration_name):
    environment = app.config.get("FICHAJE_ENV")
    if environment != "production":
        raise RuntimeError(
            f"{integration_name} is disabled outside the production environment."
        )
    if app.config.get(config_key) is not True:
        raise RuntimeError(
            f"{integration_name} requires the explicit {config_key}=True setting."
        )
