import importlib

from cpm_cli import __main__ as cli_entry
import pytest


def test_console_module_entrypoint_delegates_to_cli_main(monkeypatch):
    cli_main = importlib.import_module("cpm_cli.main")
    monkeypatch.setattr(cli_main, "main", lambda: 7)

    assert cli_entry.run() == 7
    assert cli_entry.main() == 7


def test_dispatch_supports_pkg_colon_alias(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_main = importlib.import_module("cpm_cli.main")
    code = cli_main.main(["pkg:list"], start_dir=tmp_path)

    assert code == 0
    assert "[cpm:pkg] no packages installed" in capsys.readouterr().out


def test_dispatch_supports_embed_status_alias(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_main = importlib.import_module("cpm_cli.main")
    code = cli_main.main(["embed:status"], start_dir=tmp_path)

    assert code == 0
    assert "[cpm:embed] no embedding providers configured" in capsys.readouterr().out
