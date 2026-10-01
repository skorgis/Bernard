"""Tests for the greeting module."""

import pytest

from tirol_hackathon_bernard_gruppe.greeting import greet


def test_greet_returns_message_with_name() -> None:
    """greet() includes the given name in its return value."""
    assert greet("Ada") == "Hello, Ada!"


def test_greet_rejects_empty_name() -> None:
    """greet() raises ValueError for empty or blank names."""
    with pytest.raises(ValueError, match="name must not be empty"):
        greet("   ")
