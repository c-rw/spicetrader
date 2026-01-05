from __future__ import annotations

from typing import Any, Mapping, Optional


class ConfigError(ValueError):
    pass


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def require(config: Mapping[str, Any], key: str) -> Any:
    if key not in config or _is_blank(config.get(key)):
        raise ConfigError(
            f"Missing required config key: {key}. "
            "This project is env-driven; set it in .env (or Docker Compose env_file)."
        )
    return config[key]


def optional(config: Mapping[str, Any], key: str) -> Optional[Any]:
    value = config.get(key)
    return None if _is_blank(value) else value


def require_int(config: Mapping[str, Any], key: str) -> int:
    value = require(config, key)
    try:
        return int(value)
    except Exception as e:
        raise ConfigError(f"Config key {key} must be an int, got {value!r}") from e


def require_float(config: Mapping[str, Any], key: str) -> float:
    value = require(config, key)
    try:
        return float(value)
    except Exception as e:
        raise ConfigError(f"Config key {key} must be a float, got {value!r}") from e


def require_bool(config: Mapping[str, Any], key: str) -> bool:
    value = require(config, key)
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off"}:
        return False
    raise ConfigError(f"Config key {key} must be a boolean, got {value!r}")
