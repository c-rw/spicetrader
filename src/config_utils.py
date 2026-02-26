from __future__ import annotations

import logging
from typing import Any, List, Mapping, Optional

logger = logging.getLogger(__name__)


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


# ---- Startup validation ----
# All keys required by at least one component.  Checked once at boot so
# missing config surfaces immediately instead of minutes into a live run.

_REQUIRED_KEYS: List[str] = [
    # Core bot
    'DRY_RUN', 'LOG_LEVEL', 'API_CALL_DELAY',
    # Trading
    'ORDER_SIZE', 'MAX_TOTAL_EXPOSURE', 'MAX_PER_COIN',
    # Shared strategy
    'HISTORY_SIZE', 'MIN_PROFIT_TARGET',
    # SMA Crossover
    'FAST_SMA_PERIOD', 'SLOW_SMA_PERIOD', 'MIN_HOLD_TIME', 'ENABLE_TREND_FILTER',
    # Mean Reversion
    'RSI_PERIOD', 'RSI_OVERSOLD', 'RSI_OVERBOUGHT',
    'BB_PERIOD', 'BB_STD_DEV',
    'AUTO_DETECT_LEVELS', 'USE_FIBONACCI', 'FIB_LOOKBACK_PERIOD', 'FIB_TOLERANCE',
    # MACD
    'MACD_FAST', 'MACD_SLOW', 'MACD_SIGNAL', 'MACD_HISTOGRAM_CONFIRM',
    # Breakout
    'ATR_PERIOD', 'ATR_MULTIPLIER', 'VOLUME_THRESHOLD', 'BREAKOUT_LOOKBACK', 'REQUIRE_RETEST',
    # Grid
    'GRID_SIZE', 'GRID_SPACING_PCT',
    # Market analyzer / adaptive
    'ADX_STRONG_TREND', 'ADX_WEAK_TREND',
    'CHOPPINESS_CHOPPY', 'CHOPPINESS_TRENDING',
    'RANGE_TIGHT', 'RANGE_MODERATE',
    'ADX_PERIOD', 'CHOP_PERIOD', 'SLOPE_PERIOD', 'RANGE_PERIOD',
    'ANALYSIS_CACHE_TTL',
    'REANALYSIS_INTERVAL', 'SWITCH_COOLDOWN', 'CONFIRMATIONS_REQUIRED', 'MAX_SWITCHES_PER_DAY',
    # Fees
    'MAKER_FEE', 'TAKER_FEE', 'TRACK_FEES',
]


def validate_config(config: Mapping[str, Any]) -> List[str]:
    """Validate that all required config keys are present.

    Args:
        config: Configuration mapping (typically ``dict(os.environ)``).

    Returns:
        List of missing key names (empty if all present).

    Raises:
        ConfigError: If any required keys are missing.
    """
    missing = [key for key in _REQUIRED_KEYS if key not in config or _is_blank(config.get(key))]

    if missing:
        msg = (
            f"Missing {len(missing)} required config key(s): {', '.join(sorted(missing))}. "
            "Copy .env.example to .env and fill in all values."
        )
        logger.error(msg)
        raise ConfigError(msg)

    return missing
