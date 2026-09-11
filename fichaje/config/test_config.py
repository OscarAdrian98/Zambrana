class TestConfig:
    TESTING = True
    SECRET_KEY = "fichaje-test-secret-key-not-for-production"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False


def assert_safe_test_database_uri(uri):
    """Abort test startup unless the database is an isolated SQLite database."""
    normalized_uri = (uri or "").strip().lower()
    if not normalized_uri.startswith("sqlite://"):
        raise RuntimeError(
            "Unsafe test database URI: tests may only use SQLite and must never "
            "contain the real database host or database name."
        )
