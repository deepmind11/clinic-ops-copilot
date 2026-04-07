"""Smoke tests to verify the package imports cleanly."""

import clinic_ops_copilot


def test_version() -> None:
    assert clinic_ops_copilot.__version__ == "0.1.0"


def test_cli_app_loads() -> None:
    from clinic_ops_copilot.cli.main import app

    assert app.info.name == "clinicops"
