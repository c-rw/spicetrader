# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in SpiceTrader, please report it by:

1. **Email**: Open a private security advisory on GitHub
2. **Do NOT** open a public issue for security vulnerabilities
3. **Include**:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We will respond within 48 hours and provide a timeline for fixes.

## Security Best Practices

### API Key Security

- **NEVER** commit your `.env` file or share API keys
- **Use read-only API keys** when possible
- **Limit API key permissions** to only what's needed (trading, balance queries)
- **Rotate keys regularly** - especially after testing or debugging
- **Enable 2FA** on your Kraken account
- **Whitelist IP addresses** if your server has a static IP

### Safe Deployment

1. **Always start in dry-run mode**: Set `DRY_RUN=true` in `.env`
2. **Test thoroughly**: Run for 24-48 hours in dry-run before going live
3. **Use small position sizes**: Start with minimal `ORDER_SIZE` and `MAX_PER_COIN`
4. **Monitor actively**: Check logs and database regularly when first deployed
5. **Set conservative limits**: Use `MAX_TOTAL_EXPOSURE=25` initially (not 75%)

### Docker Security

- **Don't expose ports** publicly unless using authentication
- **Keep images updated**: Rebuild regularly with `docker-compose build --no-cache`
- **Limit container resources**: Memory limits already set in docker-compose.yml
- **Use non-root user**: Container runs as non-root by default

### Database Security

- **Backup regularly**: Copy `data/trading.db` before major changes
- **Protect access**: Database contains trading history and positions
- **Don't expose**: SQLite file should never be web-accessible

## Known Security Considerations

### Trading Risks

This bot **executes real trades** with real money. Security considerations:

- **Market risk**: Crypto markets are volatile, losses are possible
- **Strategy risk**: No strategy is guaranteed profitable
- **API risk**: Exchange downtime or API changes can affect trading
- **Code risk**: Bugs can lead to unexpected trades

### AGPL-3.0 License Implications

This project is licensed under AGPL-3.0, which means:

- **Network use = distribution**: If you modify and run this on a server, you must share your modifications
- **No warranty**: This software comes with NO WARRANTY - use at your own risk
- **See LICENSE** for full legal terms

## Responsible Disclosure

We appreciate security researchers who:

- Report vulnerabilities privately first
- Give us reasonable time to fix issues before public disclosure
- Don't exploit vulnerabilities for malicious purposes

Thank you for helping keep SpiceTrader secure!
