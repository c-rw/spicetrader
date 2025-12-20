# Changelog

All notable changes to SpiceTrader will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-11-26

### Added

- AGPL-3.0 license for open source release
- CONTRIBUTING.md with development setup and PR guidelines
- SECURITY.md with security best practices and vulnerability reporting
- CHANGELOG.md for tracking project changes

### Fixed

- **Critical**: Fixed data collection logic in `coin_trader.py` that prevented bot from progressing past "Collecting data (1/50)"
  - Moved data collection check before reanalysis interval check
  - Removed `last_analysis_time` update during data collection phase
- **Critical**: Fixed TypeError crash in market analysis when reaching 50 data points
  - Convert deques to lists before passing to analyzer (deques don't support slicing)
- Applied same critical fixes to `adaptive_bot.py` for consistency

### Changed

- Optimized SMA Crossover strategy startup time
  - Reduced `SLOW_SMA_PERIOD` from 200 to 120 (4 minutes vs 11 minutes to start trading)
- Improved Mean Reversion signal frequency
  - Adjusted RSI thresholds from 40/60 to 35/65 for more opportunities in volatile crypto markets
- Optimized adaptive timing parameters
  - `REANALYSIS_INTERVAL`: 300s → 600s (10 minutes between market state checks)
  - `SWITCH_COOLDOWN`: 1800s → 1200s (20 minutes between strategy switches)

### Deprecated

- `src/bot.py` - Legacy single-strategy bot deprecated in favor of `adaptive_bot.py`
  - Users should migrate to `adaptive_bot.py` for single-coin or `multi_coin_bot.py` for portfolio trading
  - Note: this legacy entrypoint has since been removed (see [Unreleased])

### Security

- Added CLAUDE.md to .gitignore to protect internal development documentation
- Documented API key security best practices in SECURITY.md
- Added safe deployment guidelines (dry-run mode, conservative position sizing)

## [Unreleased]

### Added (Unreleased)

- `src/market_data.py`: OHLC candle caching with committed-candle series (drops Kraken's final uncommitted candle)
- `OHLC_INTERVAL` config option for indicator calculations
- AssetPairs-based order normalization (rounding to `tick_size` / decimals and enforcing `ordermin` / `costmin`)
- `pyproject.toml` to support clean editable installs (`pip install -e .`)
- Tests:
  - `tests/test_market_data.py` (OHLC cache behavior)
  - `tests/test_strategies_ohlc.py` (SMA/MACD/Mean Reversion on synthetic committed OHLC)
  - `tests/test_order_normalization.py` (rounding + minimum enforcement)
- `scripts/smoke_dry_run.py` dry-run smoke script (no network / no order placement) runnable via `python -m scripts.smoke_dry_run`

### Changed (Unreleased)

- Standardized imports to package-style (`src.*` / relative imports) and removed `sys.path` manipulation
- Docker default command runs as a module (`python -m src.multi_coin_bot`) and container runs as a non-root user (UID `10001`)
- Bots/strategies prefer committed OHLC series when available (ticker fallback only)
- Docs updated to reflect module-style execution and order normalization behavior

### Fixed (Unreleased)

- Breakout strategy now uses per-candle OHLC highs/lows/volume instead of 24h ticker fields

### Removed (Unreleased)

- `src/bot.py` legacy single-strategy entrypoint (use `src/adaptive_bot.py` or `src/multi_coin_bot.py`)

### Planned Features

- Backtesting engine for historical strategy comparison
- WebUI dashboard for real-time monitoring
- Machine learning for adaptive parameter tuning
- Multi-exchange support beyond Kraken
- Advanced risk management with stop-loss orders

---

## Release Notes

### Version 1.0.0 - Initial Public Release

This is the first public release of SpiceTrader. The bot has been tested in production and is ready for community use.

**Key Features**:

- Multi-coin adaptive trading with 5 strategies (Mean Reversion, SMA Crossover, MACD, Breakout, Grid Trading)
- Automatic market analysis and strategy selection
- Portfolio-level position sizing and exposure management
- SQLite database for trade tracking and performance analytics
- Docker deployment with docker-compose
- Comprehensive logging and dry-run mode for safe testing

**Before You Trade**:

1. Always start in dry-run mode (`DRY_RUN=true` in `.env`)
2. Test for 24-48 hours before going live
3. Use conservative position sizes initially
4. Read SECURITY.md for best practices
5. Monitor logs and database regularly

**Getting Help**:

- See CONTRIBUTING.md for development setup
- Open GitHub issues for bugs or feature requests
- Join discussions for general questions

Thank you for using SpiceTrader!

---

[1.0.0]: https://github.com/yourusername/spicetrader/releases/tag/v1.0.0
