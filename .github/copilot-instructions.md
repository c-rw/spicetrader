# Copilot Instructions

> **Global rules**: See [workspace copilot-instructions](../../../.github/copilot-instructions.md)
> **Tech persona**: See [python-agent](../../../.github/agents/python-agent.md)

> 🔓 **PUBLIC REPOSITORY** — All content is publicly visible. See [Public Repo Rules](#public-repo-rules) below.

## Overview

Adaptive multi-strategy trading bot for the Kraken cryptocurrency exchange. Python application with Docker deployment and MIT license.

## Commands

| Command | Description |
|---------|-------------|
| `python -m src.multi_coin_bot` | Run the trading bot |
| `pytest` | Run tests |
| `pytest --cov` | Run tests with coverage |
| `black .` | Format code |
| `flake8` | Lint code |
| `mypy .` | Type checking |

## Architecture

```
├── src/                  # Main application code
│   └── multi_coin_bot/   # Entry point module
├── tests/                # Test suite
├── scripts/              # Utility scripts
├── api/                  # API layer
├── ui/                   # UI components
├── deploy.sh             # Deployment script
├── pyproject.toml        # Project config and dependencies
├── CHANGELOG.md          # Version history
├── CONTRIBUTING.md       # Contribution guidelines
├── SECURITY.md           # Security policy
├── DOCKER.md             # Docker documentation
└── .env.example          # Environment variable template
```

**Data flow**: Bot entry point → strategy modules → Kraken API (via krakenex + websocket-client) → trade execution and logging

## Tech Stack

- **Language**: Python 3.10+
- **Package Management**: pip + pyproject.toml
- **Exchange API**: krakenex, websocket-client
- **Data Processing**: pandas, numpy
- **Configuration**: python-dotenv
- **Logging**: colorlog
- **Testing**: pytest + pytest-cov + pytest-asyncio
- **Code Quality**: black, flake8, mypy
- **License**: MIT

## Key Conventions

- Type hints on all functions (enforced by mypy)
- Black formatting (no config overrides)
- Flake8 linting compliance
- Async patterns for websocket connections
- See `CONTRIBUTING.md` for contribution guidelines

## Environment Variables

See `.env.example` for the full list. Key categories:

| Category | Variables |
|----------|-----------|
| **Kraken API** | API key, API secret |
| **Trading Config** | Trading pairs, strategy parameters |
| **Bot Settings** | Logging level, operational flags |

> ⚠️ **Never commit actual values** — use `.env` files (gitignored) only.

## Deployment

- **Docker**: python:3.10.16-slim base image
- **Security**: Non-root user (`appuser`) in container
- **Orchestration**: Docker Compose with port mapping
- **Deploy script**: `deploy.sh`
- See `DOCKER.md` for detailed Docker instructions

## Git Conventions

- Remote: `github.com/c-rw/spicetrader`
- **Feature branch workflow** — active feature branches
- **PR-based workflow only**
- Follow `CHANGELOG.md` format for version documentation

## Public Repo Rules

🚨 **This is a public repository. All commits and history are publicly visible.**

- **No secrets**: Never commit API keys, tokens, passwords, or connection strings
- **No personal information**: No real names, addresses, account numbers, or PII
- **No private repo references**: Do not reference private repositories, internal tools, or proprietary systems
- **PR workflow**: All changes via feature branches and pull requests — no direct pushes to `main`
- **Review before commit**: Double-check all staged changes for sensitive data before committing
