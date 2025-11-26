# Docker Deployment Guide

This guide explains how to run the SpiceTrader multi-coin bot using Docker and Docker Compose.

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 1.29+
- Valid Kraken API credentials
- Configured `.env` file

## Quick Start

### 1. Ensure .env File Exists

Make sure you have a properly configured `.env` file in the root directory:

```bash
# Copy from example if needed
cp .env.example .env

# Edit with your credentials
nano .env
```

**Required settings:**
- `KRAKEN_API_KEY` - Your Kraken API key
- `KRAKEN_API_SECRET` - Your Kraken API secret
- `DRY_RUN=true` - Start with dry-run mode for testing

### 2. Build and Start the Container

```bash
# Build and start in detached mode
docker-compose up -d

# Or rebuild if you made changes
docker-compose up -d --build
```

### 3. Monitor the Bot

```bash
# View real-time logs
docker-compose logs -f

# View just the latest logs
docker-compose logs --tail=100

# Check container status
docker-compose ps
```

### 4. Stop the Bot

```bash
# Stop the container (keeps data)
docker-compose stop

# Stop and remove container (keeps data in volumes)
docker-compose down

# Stop and remove everything including volumes (DELETES DATA)
docker-compose down -v
```

## Configuration

### Environment Variables

All configuration is done through the `.env` file. The Docker container will automatically use these settings.

**Important settings:**
```bash
# Trading mode
DRY_RUN=true              # Keep true for testing
TRADING_PAIRS=XBTUSD,SOLUSD,ETHUSD,XMRUSD

# API credentials
KRAKEN_API_KEY=your_key
KRAKEN_API_SECRET=your_secret

# Logging
LOG_LEVEL=INFO
```

### Persistent Data

The following directories are mounted as volumes to persist data:

- `./logs` - Bot logs (multi_coin_bot.log)
- `./data` - Trading database (trading.db)

These directories are created automatically if they don't exist.

## Resource Limits

Default resource limits (can be adjusted in docker-compose.yml):

- **CPU**: Max 1.0 core, Reserved 0.25 core
- **Memory**: Max 512MB, Reserved 256MB

To adjust:
```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'        # Increase if needed
      memory: 1G
```

## Logs and Monitoring

### View Logs

```bash
# Real-time logs from Docker
docker-compose logs -f spicetrader

# Follow the bot's log file directly
tail -f logs/multi_coin_bot.log

# Search for specific events
grep "SWITCHING" logs/multi_coin_bot.log
grep "Signal: BUY" logs/multi_coin_bot.log
```

### Check Health Status

```bash
# Check if container is healthy
docker-compose ps

# View health check logs
docker inspect --format='{{json .State.Health}}' spicetrader-multibot | jq
```

### Access Trading Database

```bash
# Enter the container
docker-compose exec spicetrader bash

# Then inside the container
cd /app/src
python report.py
```

Or from your host:
```bash
cd src
../venv/bin/python report.py
```

## Troubleshooting

### Container Won't Start

**Check logs:**
```bash
docker-compose logs spicetrader
```

**Common issues:**
- Missing `.env` file → Create from `.env.example`
- Invalid API credentials → Check Kraken API settings
- Port conflicts → Not applicable (this bot doesn't expose ports)

### Container Keeps Restarting

```bash
# Check logs for errors
docker-compose logs --tail=50 spicetrader

# Check container status
docker-compose ps
```

**Common causes:**
- Invalid configuration in `.env`
- API authentication failures
- Insufficient resources

### Update .env Configuration

If you modify `.env`, restart the container:

```bash
docker-compose restart
```

### Clear Logs

```bash
# Logs are automatically rotated (max 3 files, 10MB each)
# To manually clear:
rm logs/multi_coin_bot.log
docker-compose restart
```

## Advanced Usage

### Running Different Bots

To run the single-coin adaptive bot instead:

Edit `docker-compose.yml`:
```yaml
command: ["python", "src/adaptive_bot.py"]
```

Then restart:
```bash
docker-compose up -d --build
```

### Running Multiple Instances

To run multiple bots (e.g., different trading pairs):

Create a second compose file `docker-compose.btc.yml`:
```yaml
version: '3.8'

services:
  spicetrader-btc:
    extends:
      file: docker-compose.yml
      service: spicetrader
    container_name: spicetrader-btc
    env_file:
      - .env.btc
    volumes:
      - ./logs/btc:/app/logs
      - ./data/btc:/app/data
```

Run:
```bash
docker-compose -f docker-compose.btc.yml up -d
```

### Development Mode

For development with live code reloading, mount the source code:

```yaml
volumes:
  - ./src:/app/src:ro        # Mount source as read-only
  - ./logs:/app/logs
  - ./data:/app/data
```

Then restart when you make changes:
```bash
docker-compose restart
```

### Custom Python Command

Run one-off commands:

```bash
# Check connection
docker-compose exec spicetrader python -c "from kraken.client import KrakenClient; import os; from dotenv import load_dotenv; load_dotenv(); client = KrakenClient(os.getenv('KRAKEN_API_KEY'), os.getenv('KRAKEN_API_SECRET')); print('Balance:', client.get_account_balance())"

# Run report
docker-compose exec spicetrader python src/report.py

# Access Python shell
docker-compose exec spicetrader python
```

## Production Deployment

### Security Best Practices

1. **Protect .env file:**
   ```bash
   chmod 600 .env
   ```

2. **Use secrets management:**
   Consider Docker secrets or external secret management for production.

3. **Network isolation:**
   Add network configuration if needed:
   ```yaml
   networks:
     - trading_network
   ```

4. **Enable monitoring:**
   Integrate with monitoring solutions (Prometheus, Grafana, etc.)

### Automatic Updates

Create a cron job to rebuild periodically:

```bash
# /etc/cron.daily/spicetrader-update
#!/bin/bash
cd /mnt/Unraid/Repo/spicetrader
git pull
docker-compose up -d --build
```

### Backup Strategy

Backup important data:

```bash
#!/bin/bash
# backup-trading-data.sh
DATE=$(date +%Y%m%d)
tar -czf backup-${DATE}.tar.gz logs/ data/
```

## Docker Commands Reference

### Build
```bash
docker-compose build              # Build image
docker-compose build --no-cache   # Rebuild from scratch
```

### Start/Stop
```bash
docker-compose up -d              # Start detached
docker-compose stop               # Stop container
docker-compose restart            # Restart container
docker-compose down               # Stop and remove container
```

### Logs
```bash
docker-compose logs               # View all logs
docker-compose logs -f            # Follow logs
docker-compose logs --tail=50     # Last 50 lines
```

### Exec
```bash
docker-compose exec spicetrader bash           # Shell access
docker-compose exec spicetrader python src/... # Run Python
```

### Cleanup
```bash
docker-compose down -v            # Remove volumes (DELETES DATA)
docker system prune -a            # Clean unused images
```

## Performance Tips

1. **Adjust API delays** if running multiple containers:
   ```bash
   API_CALL_DELAY=3.0
   ```

2. **Monitor resource usage:**
   ```bash
   docker stats spicetrader-multibot
   ```

3. **Check logs regularly** for performance issues

4. **Use log rotation** (already configured)

## Support

If you encounter issues:

1. Check logs: `docker-compose logs --tail=100`
2. Verify `.env` configuration
3. Test API connection manually
4. Check Docker resources: `docker stats`
5. Review Kraken API status: https://status.kraken.com/

## Migration from Manual Installation

If you're currently running without Docker:

1. **Stop existing bot:**
   ```bash
   # If running as systemd service
   sudo systemctl stop spicetrader

   # Or kill the process
   pkill -f multi_coin_bot.py
   ```

2. **Backup data:**
   ```bash
   cp -r logs logs.backup
   cp -r data data.backup
   ```

3. **Start Docker version:**
   ```bash
   docker-compose up -d
   ```

4. **Verify it's working:**
   ```bash
   docker-compose logs -f
   ```

Your existing logs and database will be used by the Docker container since they're mounted as volumes.

## Summary

The Docker deployment provides:
- Isolated environment
- Easy deployment and updates
- Automatic restarts
- Resource management
- Consistent behavior across systems

**Recommended workflow:**
1. Start with `DRY_RUN=true`
2. Monitor logs for 24-48 hours
3. Verify behavior matches expectations
4. Only then set `DRY_RUN=false` for live trading

**Remember:** Always test thoroughly before live trading!
