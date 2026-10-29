"""seed 与 CLI 冒烟。"""

from __future__ import annotations

from app.cli import app
from typer.testing import CliRunner


def test_version():
    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "FlightHunter" in result.output


def test_doctor(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Doctor" in result.output or "版本" in result.output


def test_seed_and_discover(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["seed", "--safe"])
    assert result.exit_code == 0, result.output
    result2 = runner.invoke(app, ["discover", "--dry-run"])
    assert result2.exit_code == 0, result2.output
    assert (
        "DRY-RUN" in result2.output
        or "dry-run" in result2.output.lower()
        or "已登记" in result2.output
    )


def test_list_trips_after_seed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(app, ["seed", "--safe"])
    result = runner.invoke(app, ["list-trips"])
    assert result.exit_code == 0
    assert "日本" in result.output or "行程" in result.output
