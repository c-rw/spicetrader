"""Tests for config_utils.py — validation, require/optional helpers, type coercions."""
from __future__ import annotations

import pytest

from src.config_utils import (
    ConfigError,
    validate_config,
    require,
    optional,
    require_int,
    require_float,
    require_bool,
    _REQUIRED_KEYS,
    _is_blank,
)


# ---------------------------------------------------------------------------
# _is_blank
# ---------------------------------------------------------------------------

class TestIsBlank:
    def test_none_is_blank(self):
        assert _is_blank(None) is True

    def test_empty_string_is_blank(self):
        assert _is_blank("") is True

    def test_whitespace_is_blank(self):
        assert _is_blank("   ") is True

    def test_nonblank_string(self):
        assert _is_blank("hello") is False

    def test_zero_is_not_blank(self):
        assert _is_blank(0) is False

    def test_false_is_not_blank(self):
        assert _is_blank(False) is False


# ---------------------------------------------------------------------------
# require / optional
# ---------------------------------------------------------------------------

class TestRequire:
    def test_returns_value(self):
        assert require({"FOO": "bar"}, "FOO") == "bar"

    def test_missing_key_raises(self):
        with pytest.raises(ConfigError, match="Missing required config key: FOO"):
            require({}, "FOO")

    def test_blank_value_raises(self):
        with pytest.raises(ConfigError):
            require({"FOO": ""}, "FOO")

    def test_none_value_raises(self):
        with pytest.raises(ConfigError):
            require({"FOO": None}, "FOO")


class TestOptional:
    def test_returns_value_when_present(self):
        assert optional({"KEY": "val"}, "KEY") == "val"

    def test_returns_none_when_missing(self):
        assert optional({}, "KEY") is None

    def test_returns_none_for_blank(self):
        assert optional({"KEY": ""}, "KEY") is None
        assert optional({"KEY": None}, "KEY") is None


# ---------------------------------------------------------------------------
# Typed helpers
# ---------------------------------------------------------------------------

class TestRequireInt:
    def test_valid_int_string(self):
        assert require_int({"N": "42"}, "N") == 42

    def test_actual_int(self):
        assert require_int({"N": 7}, "N") == 7

    def test_non_int_raises(self):
        with pytest.raises(ConfigError, match="must be an int"):
            require_int({"N": "abc"}, "N")


class TestRequireFloat:
    def test_valid_float_string(self):
        assert require_float({"F": "3.14"}, "F") == pytest.approx(3.14)

    def test_non_float_raises(self):
        with pytest.raises(ConfigError, match="must be a float"):
            require_float({"F": "not-a-number"}, "F")


class TestRequireBool:
    @pytest.mark.parametrize("val", ["true", "True", "1", "yes", "y", "on"])
    def test_truthy_values(self, val):
        assert require_bool({"B": val}, "B") is True

    @pytest.mark.parametrize("val", ["false", "False", "0", "no", "n", "off"])
    def test_falsy_values(self, val):
        assert require_bool({"B": val}, "B") is False

    def test_actual_bool(self):
        assert require_bool({"B": True}, "B") is True
        assert require_bool({"B": False}, "B") is False

    def test_invalid_raises(self):
        with pytest.raises(ConfigError, match="must be a boolean"):
            require_bool({"B": "maybe"}, "B")


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------

def _full_config() -> dict:
    """Build a config dict with all required keys set to dummy values."""
    return {key: "1" for key in _REQUIRED_KEYS}


class TestValidateConfig:
    def test_all_keys_present_passes(self):
        """No exception when all required keys are present."""
        missing = validate_config(_full_config())
        assert missing == []

    def test_missing_single_key_raises(self):
        cfg = _full_config()
        del cfg["DRY_RUN"]
        with pytest.raises(ConfigError, match="DRY_RUN"):
            validate_config(cfg)

    def test_missing_multiple_keys_raises(self):
        cfg = _full_config()
        del cfg["DRY_RUN"]
        del cfg["ORDER_SIZE"]
        with pytest.raises(ConfigError, match="Missing 2 required config key"):
            validate_config(cfg)

    def test_blank_value_treated_as_missing(self):
        cfg = _full_config()
        cfg["MAKER_FEE"] = ""
        with pytest.raises(ConfigError, match="MAKER_FEE"):
            validate_config(cfg)

    def test_none_value_treated_as_missing(self):
        cfg = _full_config()
        cfg["TAKER_FEE"] = None
        with pytest.raises(ConfigError, match="TAKER_FEE"):
            validate_config(cfg)

    def test_extra_keys_are_ignored(self):
        """Extra keys beyond _REQUIRED_KEYS should not cause errors."""
        cfg = _full_config()
        cfg["MY_CUSTOM_KEY"] = "whatever"
        missing = validate_config(cfg)
        assert missing == []

    def test_required_keys_list_not_empty(self):
        """Sanity: the required keys list should contain entries."""
        assert len(_REQUIRED_KEYS) > 20
