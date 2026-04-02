"""
Tests for config.py — environment variable loading and validation.
"""

import os

import pytest

from backend.config import ConfigurationError, Settings


def test_missing_required_env_var_raises_clear_error() -> None:
    """
    Accessing a required setting that is not in the environment must
    raise ConfigurationError with a helpful message.

    Why test this?
    Without this check, a missing API key would cause a cryptic
    AttributeError or None-comparison failure deep inside the import
    pipeline. This test ensures the error is caught early and explains
    exactly what to do (copy .env.example to .env).
    """
    # Create a fresh Settings instance. Temporarily remove the key from
    # the environment so we can test the missing-key path.
    original = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        s = Settings()
        with pytest.raises(ConfigurationError) as exc_info:
            _ = s.anthropic_api_key
        assert "ANTHROPIC_API_KEY" in str(exc_info.value)
        assert ".env" in str(exc_info.value)
    finally:
        # Restore the original value so other tests are not affected.
        if original is not None:
            os.environ["ANTHROPIC_API_KEY"] = original


def test_optional_env_var_returns_default_when_missing() -> None:
    """
    Optional settings must return a default value when the variable is absent,
    not raise an error.
    """
    original = os.environ.pop("LOG_LEVEL", None)
    try:
        s = Settings()
        assert s.log_level == "INFO"
    finally:
        if original is not None:
            os.environ["LOG_LEVEL"] = original


def test_optional_env_var_returns_set_value() -> None:
    """
    Optional settings must return the value from the environment when set.
    """
    os.environ["LOG_LEVEL"] = "debug"
    try:
        s = Settings()
        assert s.log_level == "DEBUG"  # config.py uppercases log_level
    finally:
        del os.environ["LOG_LEVEL"]
