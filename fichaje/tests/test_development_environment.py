import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.services.integrations import require_integration
from config.development_config import (
    load_development_config,
    validate_development_database_uri,
)
import run_dev


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_clean_import(environment):
    child_environment = os.environ.copy()
    child_environment.pop("FICHAJE_TESTING", None)
    child_environment.pop("FICHAJE_ENV", None)
    child_environment.update(environment)
    return subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            (
                "import sys; import app; "
                "assert 'config.config' not in sys.modules; "
                "assert 'config.secret_config' not in sys.modules"
            ),
        ],
        cwd=PROJECT_ROOT,
        env=child_environment,
        capture_output=True,
        text=True,
        timeout=20,
    )


def _development_environment(**overrides):
    environment = {
        "FICHAJE_DEV_DB_HOST": "127.0.0.1",
        "FICHAJE_DEV_DB_NAME": "fichaje_dev",
        "FICHAJE_DEV_DB_USER": "fichaje_dev",
        "FICHAJE_DEV_DB_PASSWORD": "local-test-placeholder",
        "FICHAJE_DEV_SECRET_KEY": "local-test-secret",
    }
    environment.update(overrides)
    return environment


def test_sqlite_test_environment_is_still_isolated(app):
    assert app.config["TESTING"] is True
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite:///:memory:"
    assert app.config["FICHAJE_ENV"] == "test"
    assert "config.config" not in sys.modules
    assert "config.secret_config" not in sys.modules


def test_development_builds_only_the_local_mysql_uri():
    config = load_development_config(_development_environment())
    parsed = validate_development_database_uri(
        config["SQLALCHEMY_DATABASE_URI"]
    )
    assert parsed.drivername.startswith("mysql")
    assert parsed.host == "127.0.0.1"
    assert parsed.port == 3306
    assert parsed.database == "fichaje_dev"
    assert parsed.username == "fichaje_dev"
    assert config["TESTING"] is False


def test_empty_development_environment_does_not_fall_back_to_real_process_env():
    with pytest.raises(RuntimeError, match="Missing local"):
        load_development_config({})


@pytest.mark.parametrize(
    "overrides",
    [
        {"FICHAJE_DEV_DB_HOST": "db.invalid"},
        {"FICHAJE_DEV_DB_NAME": "another_database"},
        {"FICHAJE_DEV_DB_USER": "root"},
    ],
)
def test_development_rejects_nonlocal_or_wrong_database_settings(overrides):
    with pytest.raises(RuntimeError):
        load_development_config(_development_environment(**overrides))


def test_development_import_does_not_load_real_configuration():
    result = _run_clean_import(
        {
            "FICHAJE_ENV": "development",
            **_development_environment(),
        }
    )
    assert result.returncode == 0, result.stderr


def test_production_is_not_selected_by_default():
    result = _run_clean_import({})
    assert result.returncode != 0
    assert "FICHAJE_ENV must be explicitly set" in result.stderr


def test_invalid_environment_aborts():
    result = _run_clean_import({"FICHAJE_ENV": "invalid"})
    assert result.returncode != 0
    assert "FICHAJE_ENV must be explicitly set" in result.stderr


def test_external_services_are_disabled_in_development():
    config = load_development_config(_development_environment())
    assert config["ALLOW_EMAILS"] is False
    assert config["ALLOW_DISCORD"] is False
    assert config["ALLOW_PUSH"] is False
    assert config["ALLOW_AUTOFICHAJE"] is False


@pytest.mark.parametrize(
    ("key", "name"),
    [
        ("ALLOW_EMAILS", "Email"),
        ("ALLOW_DISCORD", "Discord"),
        ("ALLOW_PUSH", "Push"),
        ("ALLOW_AUTOFICHAJE", "Automatic clock-out"),
    ],
)
def test_integration_guards_abort_outside_production(
    app, monkeypatch, key, name
):
    monkeypatch.setitem(app.config, "FICHAJE_ENV", "development")
    monkeypatch.setitem(app.config, key, True)
    with pytest.raises(RuntimeError, match="disabled outside"):
        require_integration(app, key, name)


def test_development_banner_appears_on_login(app, client, monkeypatch):
    monkeypatch.setitem(app.config, "FICHAJE_ENV", "development")
    monkeypatch.setitem(
        app.config,
        "DEVELOPMENT_BANNER",
        "ENTORNO DE DESARROLLO — DATOS LOCALES ANONIMIZADOS"
    )
    html = client.get("/login").get_data(as_text=True)
    assert 'id="development-environment-banner"' in html
    assert "DATOS LOCALES ANONIMIZADOS" in html


def test_development_banner_is_absent_in_tests(client):
    html = client.get("/login").get_data(as_text=True)
    assert 'id="development-environment-banner"' not in html


def test_run_dev_is_bound_only_to_localhost_without_waitress():
    source = (PROJECT_ROOT / "run_dev.py").read_text(encoding="utf-8")
    assert run_dev.HOST == "127.0.0.1"
    assert run_dev.PORT == 5020
    assert run_dev.DATABASE == "fichaje_dev"
    assert run_dev.USER == "fichaje_dev"
    assert "0.0.0.0" not in source
    assert "waitress" not in source.lower()
    assert 'os.environ["FICHAJE_ENV"] = "development"' in source


def test_clone_has_no_real_secret_configuration():
    assert not (PROJECT_ROOT / "config" / "secret_config.py").exists()


def test_run_dev_rejects_unsafe_uri_before_opening_connection(app):
    class SessionThatMustNotConnect:
        @staticmethod
        def execute(*args, **kwargs):
            raise AssertionError("Database connection was attempted")

    class DatabaseThatMustNotConnect:
        session = SessionThatMustNotConnect()

    with pytest.raises(RuntimeError, match="Development must use local"):
        run_dev.verify_local_connection(app, DatabaseThatMustNotConnect())


def test_operational_clones_have_guards_and_no_embedded_endpoints_or_keys():
    discord = (PROJECT_ROOT / "avisar_fichajes_discord.py").read_text(
        encoding="utf-8"
    )
    push = (PROJECT_ROOT / "send_push_notifications.py").read_text(
        encoding="utf-8"
    )
    autofichaje = (PROJECT_ROOT / "autofichar_salidas.py").read_text(
        encoding="utf-8"
    )
    assert "require_integration" in discord
    assert "require_integration" in autofichaje
    assert "discord.com/api/webhooks" not in discord
    assert "load_push_configuration()" in push
    assert "FICHAJE_ALLOW_PUSH" in push
    assert "mxdemo.com/push/" not in push
