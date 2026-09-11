import importlib
import ast
import os
from pathlib import Path
import subprocess
import sys

import pytest

from script_guards import require_production_script


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OPERATIONAL_SCRIPTS = (
    "autofichar_salidas.py",
    "generar_avisos_json.py",
    "avisar_fichajes_discord.py",
    "send_push_notifications.py",
)


@pytest.mark.parametrize("script_name", OPERATIONAL_SCRIPTS)
@pytest.mark.parametrize("environment_name", ("development", "test"))
def test_operational_script_aborts_before_writing_files(
    tmp_path,
    script_name,
    environment_name,
):
    environment = os.environ.copy()
    environment.pop("FICHAJE_TESTING", None)
    environment["FICHAJE_ENV"] = environment_name
    environment["PYTHONDONTWRITEBYTECODE"] = "1"

    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(PROJECT_ROOT / script_name),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode != 0
    assert "disabled outside production" in result.stderr
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("script_name", OPERATIONAL_SCRIPTS)
@pytest.mark.parametrize("environment_name", ("development", "test"))
def test_guard_aborts_before_flask_secrets_or_connections(
    tmp_path,
    script_name,
    environment_name,
):
    environment = os.environ.copy()
    environment.pop("FICHAJE_TESTING", None)
    environment["FICHAJE_ENV"] = environment_name
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    script_path = PROJECT_ROOT / script_name
    probe = f"""
import runpy
import socket
import sys
sys.path.insert(0, {str(PROJECT_ROOT)!r})
attempted = []
def forbidden_connect(*args, **kwargs):
    attempted.append((args, kwargs))
    raise AssertionError('connection attempted')
socket.socket.connect = forbidden_connect
try:
    runpy.run_path({str(script_path)!r}, run_name='__main__')
except RuntimeError as error:
    assert 'disabled outside production' in str(error)
else:
    raise AssertionError('guard did not abort')
assert attempted == []
assert 'app' not in sys.modules
assert 'flask' not in sys.modules
assert 'config.config' not in sys.modules
assert 'config.secret_config' not in sys.modules
print('guard-ok')
"""

    result = subprocess.run(
        [sys.executable, "-B", "-c", probe],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == "guard-ok\n"
    assert result.stderr == ""
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("script_name", OPERATIONAL_SCRIPTS)
def test_static_guard_precedes_dangerous_imports(script_name):
    source = (PROJECT_ROOT / script_name).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=script_name)
    guard_index = next(
        index
        for index, node in enumerate(tree.body)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
    )
    imported_before_guard = {
        alias.name
        for node in tree.body[:guard_index]
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    from_before_guard = {
        node.module
        for node in tree.body[:guard_index]
        if isinstance(node, ast.ImportFrom)
    }
    assert imported_before_guard <= {"os"}
    assert from_before_guard <= {"script_guards"}

    dangerous_imports = {"app", "logging", "requests", "pywebpush"}
    for index, node in enumerate(tree.body):
        imported = set()
        if isinstance(node, ast.Import):
            imported = {alias.name.split(".", 1)[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported = {node.module.split(".", 1)[0]}
        if imported & dangerous_imports:
            assert index > guard_index


def test_standalone_guard_requires_both_production_and_explicit_flag():
    with pytest.raises(RuntimeError, match="outside production"):
        require_production_script(
            "FICHAJE_ALLOW_PUSH",
            "Push",
            {"FICHAJE_ENV": "development", "FICHAJE_ALLOW_PUSH": "1"},
        )

    with pytest.raises(RuntimeError, match="explicit"):
        require_production_script(
            "FICHAJE_ALLOW_PUSH",
            "Push",
            {"FICHAJE_ENV": "production"},
        )

    require_production_script(
        "FICHAJE_ALLOW_PUSH",
        "Push",
        {"FICHAJE_ENV": "production", "FICHAJE_ALLOW_PUSH": "1"},
    )


def test_avisos_file_flow_is_independent_from_tracked_file(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    generator = importlib.import_module("generar_avisos_json")
    consumer = importlib.import_module("send_push_notifications")
    path = tmp_path / "avisos.json"
    sample = [{"email": "empleado@example.test", "mensaje": "Aviso ficticio"}]

    assert consumer.cargar_avisos(path) == []
    generator.guardar_avisos(sample, path)
    assert path.is_file()
    assert consumer.cargar_avisos(path) == sample

    generator.guardar_avisos([], path)
    assert not path.exists()
    assert consumer.cargar_avisos(path) == []


def test_importing_operational_modules_does_not_create_logs(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    for module_name in (
        "autofichar_salidas",
        "generar_avisos_json",
        "avisar_fichajes_discord",
        "send_push_notifications",
    ):
        module = importlib.import_module(module_name)
        importlib.reload(module)

    assert list(tmp_path.iterdir()) == []
