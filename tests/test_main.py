"""Tests for the command-line entry point."""

import pytest

from main import main, parse_args


def test_parse_args_defaults_to_world() -> None:
    """parse_args() defaults the name to 'World' when omitted."""
    args = parse_args([])
    assert args.name == "World"


def test_parse_args_reads_positional_name() -> None:
    """parse_args() reads the name from a positional argument."""
    args = parse_args(["Grace"])
    assert args.name == "Grace"


def test_main_prints_greeting(capsys: pytest.CaptureFixture[str]) -> None:
    """main() prints the greeting for the given name."""
    main(["Grace"])
    captured = capsys.readouterr()
    assert captured.out == "Hello, Grace!\n"
