# Contributing to SpiceTrader

Thank you for your interest in contributing to SpiceTrader! This document provides guidelines for contributing to the project.

## Development Setup

1. **Fork the repository**

   ```bash
   git clone https://github.com/yourusername/spicetrader.git
   cd spicetrader
   ```

2. **Create a virtual environment**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**

   ```bash
   cp .env.example .env
   # Edit .env with your Kraken API credentials
   ```

5. **Create a feature branch**

   ```bash
   git checkout -b feature/your-feature-name
   ```

## Code Style

- **Follow PEP 8** style guidelines
- **Use type hints** for function parameters and return values
- **Add docstrings** for classes and public methods
- **Run black** before committing: `black src/`
- **Check with flake8**: `flake8 src/`

## Testing

- **Write tests** for new features in `tests/`
- **Run all tests** before submitting PR: `pytest`
- **Test in dry-run mode** first: Set `DRY_RUN=true` in `.env`
- **Ensure coverage**: `pytest --cov=src tests/`

## Submitting Changes

1. **Commit your changes**

   ```bash
   git add .
   git commit -m "Brief description of changes"
   ```

2. **Push to your fork**

   ```bash
   git push origin feature/your-feature-name
   ```

3. **Create a Pull Request**
   - Provide clear description of changes
   - Reference any related issues
   - Ensure all tests pass
   - Include screenshots for UI changes

## Pull Request Guidelines

- **One feature per PR** - Keep PRs focused and reviewable
- **Update documentation** - Update README.md if adding features
- **Add tests** - New features should include tests
- **Follow commit conventions** - Use clear, descriptive commit messages
- **Rebase if needed** - Keep your branch up to date with main

## Bug Reports

When reporting bugs, please include:

- **Bot version** and which bot (multi_coin_bot, adaptive_bot, etc.)
- **Configuration** (without API keys!)
- **Error logs** - Full stack trace if available
- **Steps to reproduce** - Detailed steps to recreate the issue
- **Expected vs actual behavior**

## Feature Requests

For feature requests, please describe:

- **Use case** - What problem does it solve?
- **Proposed solution** - How would it work?
- **Alternatives considered** - Other approaches you've thought of
- **Priority** - Is this critical, important, or nice-to-have?

## Code Review Process

1. Maintainers will review PRs within 1-2 weeks
2. Address any feedback from reviewers
3. Once approved, maintainers will merge your PR
4. Celebrate! You're now a SpiceTrader contributor!

## Areas Where We Need Help

- **Strategy development** - Implementing new trading strategies
- **Testing** - Writing tests and improving coverage
- **Documentation** - Improving docs and examples
- **Bug fixes** - Fixing known issues
- **Performance** - Optimizing bot performance
- **Backtesting** - Adding historical testing capabilities

## Questions?

- Open a GitHub Discussion for general questions
- Open an Issue for bugs or feature requests
- Check existing issues before creating new ones

Thank you for contributing!
