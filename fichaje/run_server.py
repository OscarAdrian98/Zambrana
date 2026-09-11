"""Entrypoint local de Waitress sin efectos al importarse."""

import os


ALLOWED_HOSTS = frozenset({"0.0.0.0", "127.0.0.1"})
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5015
DEFAULT_THREADS = 4


def load_waitress_options(environ=None):
    environ = os.environ if environ is None else environ
    host = environ.get("FICHAJE_WEB_HOST", DEFAULT_HOST).strip()
    if host not in ALLOWED_HOSTS:
        raise RuntimeError("FICHAJE_WEB_HOST is not allowed.")

    try:
        port = int(environ.get("FICHAJE_WEB_PORT", str(DEFAULT_PORT)))
        threads = int(
            environ.get("FICHAJE_WAITRESS_THREADS", str(DEFAULT_THREADS))
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Waitress port and threads must be integers.") from exc

    if port != DEFAULT_PORT:
        raise RuntimeError("Local Waitress must listen on port 5015.")
    if not 1 <= threads <= 32:
        raise RuntimeError("FICHAJE_WAITRESS_THREADS must be between 1 and 32.")
    return {"host": host, "port": port, "threads": threads}


def main():
    options = load_waitress_options()
    from waitress import serve
    from app import app

    serve(app, **options)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
