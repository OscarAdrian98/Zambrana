"""Guardas sin dependencias para los scripts operativos del clon."""

import os


def flag_enabled(flag_name, environ=None):
    """Return True only for an explicit per-process opt-in."""
    environ = os.environ if environ is None else environ
    return environ.get(flag_name) == "1"


def require_production_script(flag_name, script_name, environ=None):
    environ = os.environ if environ is None else environ
    if environ.get("FICHAJE_ENV") != "production":
        raise RuntimeError(f"{script_name} is disabled outside production.")
    if not flag_enabled(flag_name, environ):
        raise RuntimeError(
            f"{script_name} requires the explicit {flag_name}=1 setting."
        )
