# SpiceTrader - Adaptive Multi-Strategy Trading Bot

A professional-grade adaptive cryptocurrency trading system for Kraken that automatically selects and switches between multiple trading strategies based on real-time market analysis.

## Table of Contents

- [What Is This?](#what-is-this)
- [Key Features](#key-features)
- [How It Works](#how-it-works)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Configuration](#configuration)
- [Understanding Strategies](#understanding-strategies)
- [Running the Bot](#running-the-bot)
- [Monitoring and Logs](#monitoring-and-logs)
- [Safety Features](#safety-features)
- [Troubleshooting](#troubleshooting)
- [Advanced Usage](#advanced-usage)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [Disclaimer](#disclaimer)

---

## What Is This?

SpiceTrader is an **intelligent trading bot** that doesn't rely on a single strategy. Instead, it:

1. **Analyzes market conditions** every 30 minutes using technical indicators (ADX, Choppiness Index, ATR, etc.)
2. **Automatically selects** the best strategy for current market conditions
3. **Switches strategies** when markets change (with safety confirmations)
4. **Trades multiple coins** independently (BTC, SOL, ETH, XMR)
5. **Manages your portfolio** with intelligent position sizing

### Example Scenario

```plaintext
15:00 - BTC ranging between $95k-$102k
        → Bot selects Mean Reversion strategy
├── scripts/
│   └── verify_dry_run.py          # Safety helper
        → Bot detects volatile breakout after 3 confirmations
        → Switches to Breakout strategy
├── data/                          # SQLite DB (runtime)
        → Trades the momentum

20:00 - SOL in strong uptrend while BTC still volatile
        → SOL uses SMA Crossover (trend following)
        → BTC still using Breakout
        → Each coin independently optimized
```

---

## Key Features

### Adaptive Intelligence
- **7 Market States Detected**: Strong uptrend, downtrend, moderate trend, range-bound, volatile breakout, choppy, low volatility
- **5 Trading Strategies**: Mean reversion, SMA crossover, MACD, breakout, grid trading
- **Automatic Strategy Selection**: Picks the optimal strategy for current conditions
- **Safe Strategy Switching**: Requires 3 confirmations, 1-hour cooldown, max 4 switches/day

### Multi-Coin Support
- **Independent Analysis**: Each coin analyzed separately
- **Different Strategies Simultaneously**: BTC can use mean reversion while SOL uses trend following
- **Portfolio Management**: Max 75% total exposure, 25% per coin
- **Smart Position Sizing**: Calculates appropriate position sizes based on account balance

### Professional Risk Management
- **Dry-Run Mode**: Test without risking real money
- **Position Limits**: Prevents over-exposure
- **Confirmation System**: Prevents over-trading
- **Comprehensive Logging**: Track every decision

---

## How It Works

### The Adaptive System

```plaintext
┌─────────────────┐
│  Market Data    │
│  (Price, Vol)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Market Analyzer │ ◄── Calculates ADX, Choppiness, ATR, Range%
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Market State   │ ◄── "Strong Uptrend" or "Range-Bound" etc.
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│Strategy Selector│ ◄── Maps state to best strategy
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│Execute Strategy │ ◄── Runs chosen strategy, generates signals
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Place Orders    │ ◄── Executes buy/sell with position sizing
└─────────────────┘
```

**Data note (important)**: For indicators like ATR/ADX and for volume-surge confirmation, the bot uses Kraken **OHLC candles** (not the 24h ticker high/low/volume). Kraken's OHLC endpoint includes a final "current" candle that is not yet committed; the bot automatically drops that last candle so calculations use committed data.

### Market State Detection

The bot uses technical indicators to classify markets:

| Indicator | Purpose | Example |
|-----------|---------|---------|
| **ADX** | Trend strength | >25 = strong trend, <20 = weak/ranging |
| **Choppiness Index** | Market directionality | >61.8 = choppy, <38.2 = trending |
| **Range %** | Price volatility | <5% = tight range, >15% = volatile |
| **Slope** | Trend direction | Positive = uptrend, negative = downtrend |
| **ATR** | Volatility measure | High ATR = volatile, low = stable |

Based on these, it classifies the market into one of **7 states**:

1. **Strong Uptrend**: ADX >25, positive slope → Use SMA Crossover
2. **Strong Downtrend**: ADX >25, negative slope → Use SMA Crossover
3. **Moderate Trend**: ADX 20-25 → Use MACD
4. **Range-Bound**: ADX <20, Range 10-15% → Use Mean Reversion
5. **Volatile Breakout**: High ATR, breaking levels → Use Breakout
6. **Choppy**: Choppiness >61.8 → Use Mean Reversion
7. **Low Volatility**: Range <5% → Use Grid Trading

---

## Quick Start

### 1. Clone and Install

```bash
cd /mnt/Unraid/Repo/spicetrader
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Get Kraken API Keys

1. Go to https://www.kraken.com/u/security/api
2. Create new API key with permissions:
   - ✅ Query Funds
   - ✅ Query Open Orders & Trades
   - ✅ Create & Modify Orders (for live trading)
3. Set **Nonce Window**: 888888888 (recommended)
4. Copy your **API Key** and **Private Key**

### 3. Configure Environment

```bash
cp .env.example .env
nano .env
```

Add your credentials:
```bash
KRAKEN_API_KEY=your_api_key_here
KRAKEN_API_SECRET=your_private_key_here

# Start with dry-run mode
DRY_RUN=true
```

### 4. Test Connection

```bash
../.venv/bin/python -c "
from src.kraken.client import KrakenClient
import os
from dotenv import load_dotenv
load_dotenv()
client = KrakenClient(os.getenv('KRAKEN_API_KEY'), os.getenv('KRAKEN_API_SECRET'))
print('Server time:', client.get_server_time())
print('Balance:', client.get_account_balance())
"
```

If you see server time and balance, you're connected!

### 5. Run Your First Bot

**Single-Coin Adaptive Bot** (BTC only):
```bash
./.venv/bin/python -m src.adaptive_bot
```

**Multi-Coin Bot** (BTC, SOL, ETH, XMR):
```bash
./.venv/bin/python -m src.multi_coin_bot
```

### Docker (Bot + Dashboard)

To run the bot plus the read-only dashboard (API + UI) together:

```bash
docker compose up -d --build
```

- UI: [http://localhost:3000](http://localhost:3000)
- API: [http://localhost:8000](http://localhost:8000)

If the bot fails at startup with a `PermissionError` writing logs, see the permissions section in [DOCKER.md](DOCKER.md).

Both run in **dry-run mode** by default (no real trades).

---

## Installation

### Prerequisites

- Python 3.8+
- Kraken account with API access
- Basic understanding of cryptocurrency trading

### Step-by-Step Installation

1. **Clone or Navigate to Repository**
   ```bash
   cd /mnt/Unraid/Repo/spicetrader
```

2. **Create Virtual Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
```

   Dependencies include:
   - `krakenex` - Kraken API wrapper
   - `requests` - HTTP library
   - `python-dotenv` - Environment management
   - `numpy` - Technical calculations
   - `pytest` - Testing (optional)

4. **Create Configuration**
   ```bash
   cp .env.example .env
```

5. **Edit Configuration**
   ```bash
   nano .env  # or use your preferred editor
```

---

## Configuration

### Essential Settings

#### API Credentials
```bash
KRAKEN_API_KEY=your_api_key_here
KRAKEN_API_SECRET=your_private_key_here
```

#### Trading Mode
```bash
# Single-coin mode (adaptive_bot.py)
TRADING_PAIR=XBTUSD

# Multi-coin mode (multi_coin_bot.py)
TRADING_PAIRS=XBTUSD,SOLUSD,ETHUSD,XMRUSD
```

#### Safety Settings
```bash
DRY_RUN=true              # IMPORTANT: Keep true until tested
LOG_LEVEL=INFO            # DEBUG, INFO, WARNING, ERROR
```

### Fee Accounting
```bash
# Kraken fee structure (as decimals)
MAKER_FEE=0.0016          # 0.16% for limit orders
TAKER_FEE=0.0026          # 0.26% for market orders

# Minimum profit thresholds
MIN_PROFIT_PERCENT=0.005  # 0.5% minimum profit after fees
SKIP_UNPROFITABLE_TRADES=true  # Skip trades that won't cover fees

# Fee tracking
TRACK_FEES=true           # Enable fee tracking and reporting
```

**Fee Tiers**: Kraken fees decrease with 30-day trading volume:
- <$50k: 0.16% maker / 0.26% taker (default)
- $50k-$100k: 0.14% maker / 0.24% taker
- $100k-$250k: 0.12% maker / 0.22% taker

Adjust `MAKER_FEE` and `TAKER_FEE` based on your tier.

### Position Sizing

```bash
# Portfolio limits
MAX_TOTAL_EXPOSURE=75     # Max % of account in all positions
MAX_PER_COIN=25           # Max % of account per single coin

# Order sizes (base currency amounts)
ORDER_SIZE=0.001          # Default order size

# Per-coin order sizes (optional)
XBTUSD_ORDER_SIZE=0.001   # 0.001 BTC
SOLUSD_ORDER_SIZE=0.1     # 0.1 SOL
ETHUSD_ORDER_SIZE=0.01    # 0.01 ETH
XMRUSD_ORDER_SIZE=0.1     # 0.1 XMR

# Market data (recommended)
OHLC_INTERVAL=1           # Candle interval in minutes (1,5,15,30,60,...)
```

### Exchange Order Rules (Automatic)

For live trading, the bot normalizes orders using Kraken `AssetPairs` metadata before submitting:
- Rounds **volume** down to allowed `lot_decimals`
- Rounds **limit price** down to `tick_size` / `pair_decimals`
- Enforces minimums like `ordermin` and `costmin` (when a price estimate is available)

If normalization causes an order to round to zero or fall below minimums, the bot will log an error and skip placing that order.

### Adaptive Settings

```bash
# Re-analysis frequency
REANALYSIS_INTERVAL=1800  # Seconds (1800 = 30 minutes)

# Strategy switching controls
SWITCH_COOLDOWN=3600          # Min time between switches (1 hour)
CONFIRMATIONS_REQUIRED=3      # Confirmations before switching
MAX_SWITCHES_PER_DAY=4        # Daily switch limit
```

### Market Analysis Thresholds

```bash
# ADX (trend strength)
ADX_STRONG_TREND=25       # Above = strong trend
ADX_WEAK_TREND=20         # Below = weak/ranging

# Choppiness Index
CHOPPINESS_CHOPPY=61.8    # Above = choppy market
CHOPPINESS_TRENDING=38.2  # Below = trending market

# Range percentage
RANGE_TIGHT=5             # Below = low volatility
RANGE_MODERATE=15         # Above = high volatility
```

### Strategy Parameters

#### Mean Reversion
```bash
RSI_PERIOD=14
RSI_OVERSOLD=40           # Buy signal threshold
RSI_OVERBOUGHT=60         # Sell signal threshold

BB_PERIOD=20              # Bollinger Bands period
BB_STD_DEV=2.0            # Standard deviations

# Support/Resistance (for BTC)
SUPPORT_LEVEL=96000       # Buy zone
RESISTANCE_LEVEL=102000   # Sell zone
SUPPORT_ZONE=3000         # Zone width
RESISTANCE_ZONE=3000
```

#### SMA Crossover
```bash
FAST_SMA_PERIOD=10        # Fast moving average
SLOW_SMA_PERIOD=30        # Slow moving average
```

#### MACD
```bash
MACD_FAST=12
MACD_SLOW=26
MACD_SIGNAL=9
```

#### Breakout
```bash
ATR_MULTIPLIER=1.5        # ATR threshold
VOLUME_THRESHOLD=1.5      # Volume surge (150% of avg, based on per-candle volume)
```

#### Grid Trading
```bash
GRID_SIZE=10              # Number of grid levels
GRID_SPACING_PCT=0.5      # Spacing between levels (%)
```

---

## Understanding Strategies

### 1. Mean Reversion

**Best For**: Range-bound markets (e.g., BTC $95k-$102k)

**How It Works**:
- Identifies support and resistance levels
- Buys when price is at support + RSI oversold + below lower Bollinger Band
- Sells when price is at resistance + RSI overbought + above upper Bollinger Band

**Example**:
```plaintext
BTC ranging $96k-$102k:
- Price drops to $96,500, RSI = 35 → BUY
- Price rises to $101,500, RSI = 65 → SELL
- Repeat while market stays in range
```

**When Selected**: Range-bound or choppy market states

---

### 2. SMA Crossover

**Best For**: Strong trending markets

**How It Works**:
- Tracks fast (10-period) and slow (30-period) moving averages
- Buys when fast crosses above slow (golden cross)
- Sells when fast crosses below slow (death cross)

**Example**:
```plaintext
SOL in strong uptrend:
- Fast SMA crosses above slow → BUY
- Ride the trend
- Fast SMA crosses below slow → SELL
```

**When Selected**: Strong uptrend or downtrend states

---

### 3. MACD

**Best For**: Moderate trends

**How It Works**:
- Calculates MACD line (12-26 EMA) and signal line (9 EMA)
- Buys when MACD crosses above signal (bullish)
- Sells when MACD crosses below signal (bearish)

**Example**:
```plaintext
ETH in moderate uptrend:
- MACD crosses above signal → BUY
- MACD crosses below signal → SELL
```

**When Selected**: Moderate trend state

---

### 4. Breakout

**Best For**: Volatile markets with clear support/resistance

**How It Works**:
- Identifies support/resistance from price history
- Detects volume surges (>150% average)
- Buys when price breaks resistance + volume surge + high ATR
- Sells when price breaks support + volume surge

**Example**:
```plaintext
BTC breaking out of range:
- Price breaks $106k + volume spike → BUY
- Ride the breakout momentum
- Price breaks back below → SELL
```

**When Selected**: Volatile breakout state

---

### 5. Grid Trading

**Best For**: Low volatility, tight ranges

**How It Works**:
- Creates grid of buy/sell levels around current price
- Places buy orders below current price
- Places sell orders above current price
- Profits from small oscillations

**Example**:
```plaintext
ETH in tight $2,450-$2,500 range:
- Grid levels: $2,450, $2,460, $2,470, $2,480, $2,490, $2,500
- Buy at lower levels, sell at upper levels
- Profits from small moves
```

**When Selected**: Low volatility state

---

## Fee Impact & Profitability

### Understanding Trading Fees

**Kraken charges fees on both sides of every trade:**
- Buy order: 0.26% fee (taker) or 0.16% (maker)
- Sell order: 0.26% fee (taker) or 0.16% (maker)
- **Round-trip cost**: ~0.52% (taker) or ~0.32% (maker)

**This means:**
- A trade must move **>0.52%** to break even (using market orders)
- Smaller price moves = unprofitable after fees
- High-frequency strategies are most affected

### Fee Tracking Features

SpiceTrader automatically tracks fees:
- ✅ **Real-time fee calculation** on every trade
- ✅ **Cumulative fee tracking** across all positions
- ✅ **Net P&L calculation** (gross profit minus fees)
- ✅ **Fee percentage** of total trading volume
- ✅ **Breakeven thresholds** displayed in logs

### Strategy-Specific Fee Impact

**High Impact** (>2% fee drag):
- 🔴 **Grid Trading**: Many small trades = high cumulative fees
  - **Solution**: Increase grid spacing (>1% per level)
  - **Example**: 10 grid levels @ 0.5% spacing = 5% in fees

- 🟡 **Mean Reversion**: Frequent oscillations between support/resistance
  - **Solution**: Wider zones, stricter entry criteria
  - **Example**: $96k-$102k range (6%) covers fees comfortably

**Medium Impact** (1-2% fee drag):
- 🟡 **MACD**: Moderate trade frequency
- 🟡 **SMA Crossover**: Depends on crossover frequency

**Low Impact** (<1% fee drag):
- 🟢 **Breakout**: Fewer, larger moves
  - **Best for fee efficiency**

### Example P&L With Fees

```plaintext
Trade Example (BTC):
Entry: $96,000 @ 0.001 BTC
Exit:  $98,000 @ 0.001 BTC

Gross Profit:
  ($98,000 - $96,000) × 0.001 = $2.00

Fees:
  Entry fee: $96,000 × 0.001 × 0.0026 = $0.25
  Exit fee:  $98,000 × 0.001 × 0.0026 = $0.25
  Total fees: $0.50

Net Profit:
  $2.00 - $0.50 = $1.50 (75% of gross)
```

### Monitoring Fees

The bot displays fee information in logs:

```plaintext
💰 Total Fees: $12.50 | Gross P&L: $45.00 | Net P&L: $32.50
```

**Key Metrics**:
- **Cumulative Fees**: Total fees paid across all trades
- **Gross P&L**: Profit before fees
- **Net P&L**: Actual profit after fees
- **Fee %**: Fees as percentage of trading volume

---

## Running the Bot

### Option 1: Single-Coin Adaptive Bot

Trades one cryptocurrency with adaptive strategy selection.

```bash
cd src
../venv/bin/python adaptive_bot.py
```

**What It Does**:
1. Collects initial market data (50+ data points)
2. Analyzes market conditions every 30 minutes
3. Selects optimal strategy
4. Switches strategies when market changes (with confirmations)
5. Executes trades based on current strategy

**Console Output**:
```plaintext
================================================================================
ADAPTIVE TRADING BOT
================================================================================
Trading Pair: XBTUSD
Dry Run: True
Strategy: Adaptive (starts with analysis)
================================================================================
✓ Connected to Kraken
Account Balance: $10,000.00
✓ Bot is running. Press Ctrl+C to stop.

--- Market Analysis ---
State: range_bound | ADX: 18.2 | Range: 12.3% | Confidence: 85%
Strategy Selected: mean_reversion

--- Trading Signal ---
Price: $96,500 (in support zone)
RSI: 35 (oversold)
Signal: BUY

[DRY RUN] BUY: 0.001000 BTC @ $96,500
```

**Configuration** (in `.env`):
```bash
TRADING_PAIR=XBTUSD
ORDER_SIZE=0.001
DRY_RUN=true
MIN_PROFIT_TARGET=0.010
MIN_HOLD_TIME=900
```

---

### Option 2: Multi-Coin Bot

Trades multiple cryptocurrencies independently.

```bash
cd src
../venv/bin/python multi_coin_bot.py
```

**What It Does**:
1. Analyzes each coin independently
2. Selects different strategies per coin
3. Manages portfolio-wide position sizing
4. Coordinates trades to stay within exposure limits

**Console Output**:
```plaintext
================================================================================
MULTI-COIN ADAPTIVE TRADING BOT
================================================================================
Trading Pairs: XBTUSD, SOLUSD, ETHUSD, XMRUSD
Dry Run: True
Max Total Exposure: 75%
Max Per Coin: 25%
================================================================================
✓ Connected to Kraken
Account Balance: $10,000.00

--- XBTUSD ---
Market: range_bound | Confidence: 85%
Strategy: mean_reversion
Signal: BUY
[DRY RUN] BUY: 0.001000 @ $96,500

--- SOLUSD ---
Market: strong_uptrend | Confidence: 90%
Strategy: sma_crossover
Signal: BUY
[DRY RUN] BUY: 0.500000 @ $145.00

--- ETHUSD ---
Market: low_volatility | Confidence: 75%
Strategy: grid
Signal: None (establishing grid)

--- XMRUSD ---
Market: moderate_trend | Confidence: 80%
Strategy: macd
Signal: None

📊 PORTFOLIO SUMMARY
--------------------------------------------------------------------------------
XBTUSD     | mean_reversion  | range_bound          | Pos: long   | Trades: 1
SOLUSD     | sma_crossover   | strong_uptrend       | Pos: long   | Trades: 1
ETHUSD     | grid            | low_volatility       | Pos: None   | Trades: 0
XMRUSD     | macd            | moderate_trend       | Pos: None   | Trades: 0
--------------------------------------------------------------------------------
```

**Configuration** (in `.env`):
```bash
TRADING_PAIRS=XBTUSD,SOLUSD,ETHUSD,XMRUSD
MAX_TOTAL_EXPOSURE=75
MAX_PER_COIN=25
DRY_RUN=true
MIN_PROFIT_TARGET=0.010
MIN_HOLD_TIME=900
```

---

### Demo Mode

Test strategies without connecting to Kraken:

```bash
cd demos

# Demo adaptive strategy selection
python demo_adaptive.py

# Demo mean reversion strategy
python demo_mean_reversion.py
```

---

## Monitoring and Logs

### Database Tracking

**All trading activity is automatically saved to a SQLite database** at `data/trading.db`.

The database tracks:
- ✅ **Every trade** with entry/exit prices and fees
- ✅ **Position P&L** (gross, fees, net)
- ✅ **Strategy performance** metrics
- ✅ **Market conditions** at time of trades
- ✅ **Strategy switches** with reasons
- ✅ **Daily/weekly summaries**

**View your trading performance:**
```bash
cd src
../venv/bin/python report.py
```

This displays:
- Daily summary (trades, P&L, win rate)
- Open positions
- Recent closed positions with P&L
- Recent trade history

### Log Files

All bots create detailed logs in the `logs/` directory:

```plaintext
logs/
├── bot.log              # Basic bot (if used)
├── adaptive_bot.log     # Single-coin adaptive bot
└── multi_coin_bot.log   # Multi-coin bot
```

### What's Logged

```plaintext
2025-01-16 15:30:00 - INFO - Market Analysis
2025-01-16 15:30:00 - INFO - [XBTUSD] Market: range_bound | Confidence: 85%
2025-01-16 15:30:00 - INFO - [XBTUSD] Strategy: mean_reversion
2025-01-16 15:30:00 - INFO - [XBTUSD] Signal: BUY
2025-01-16 15:30:00 - INFO - [XBTUSD] [DRY RUN] BUY: 0.001 @ $96,500

2025-01-16 16:00:00 - INFO - Market Analysis
2025-01-16 16:00:00 - INFO - [XBTUSD] Market: volatile_breakout | Confidence: 75%
2025-01-16 16:00:00 - INFO - [XBTUSD] New strategy recommended: breakout (current: mean_reversion)
2025-01-16 16:00:00 - INFO - [XBTUSD] Confirmation 1/3

2025-01-16 16:30:00 - INFO - [XBTUSD] Confirmation 2/3
2025-01-16 17:00:00 - INFO - [XBTUSD] Confirmation 3/3
2025-01-16 17:00:00 - INFO - [XBTUSD] 🔄 SWITCHING: mean_reversion → breakout
2025-01-16 17:00:00 - INFO - [XBTUSD] Reason: Volatile breakout detected
2025-01-16 17:00:00 - INFO - [XBTUSD] ✅ Switched (1/4 today)
```

### Viewing Logs in Real-Time

```bash
# Follow adaptive bot log
tail -f logs/adaptive_bot.log

# Follow multi-coin bot log
tail -f logs/multi_coin_bot.log

# Search for specific events
grep "SWITCHING" logs/adaptive_bot.log
grep "Signal: BUY" logs/multi_coin_bot.log
```

### Key Events to Monitor

- **Strategy Switches**: Look for "🔄 SWITCHING"
- **Trade Signals**: "Signal: BUY" or "Signal: SELL"
- **Confirmations**: "Confirmation X/3"
- **Position Updates**: "Pos: long" or "Pos: short"
- **Errors**: "ERROR" or "Failed"

---

## Safety Features

### 1. Dry-Run Mode

**Default**: Enabled (`DRY_RUN=true`)

All orders are simulated. Perfect for:
- Testing strategies
- Learning how the bot works
- Verifying configuration
- Running for days/weeks to observe behavior

**To Enable Live Trading** (after thorough testing):
```bash
DRY_RUN=false
```

⚠️ **Warning**: Only disable dry-run after you understand how the bot works!

---

### 2. Confirmation System

Prevents impulsive strategy switching:
- **3 Confirmations Required**: Market must show same state 3 times
- **30-Minute Intervals**: Between each confirmation
- **~90 Minutes Total**: Before switch happens

**Why**: Prevents switching on temporary market noise.

---

### 3. Cooldown Period

**1-Hour Minimum** between strategy switches.

**Why**: Gives each strategy time to work before changing.

---

### 4. Daily Switch Limit

**Maximum 4 switches per day** per coin.

**Why**: Prevents over-trading and excessive fees.

---

### 5. Position Sizing Limits

**Portfolio Level**:
- Max 75% total exposure across all coins
- Keeps 25% cash reserve

**Per-Coin Level**:
- Max 25% exposure per single coin
- Diversifies risk

**Example**:
```plaintext
$10,000 account:
- Max total positions: $7,500 (75%)
- Max BTC position: $2,500 (25%)
- Max SOL position: $2,500 (25%)
- etc.
```

---

### 6. API Rate Limiting

Built-in delays prevent hitting Kraken's rate limits:
```bash
API_CALL_DELAY=1.0    # Single-coin bot
API_CALL_DELAY=2.0    # Multi-coin bot (more API calls)
```

---

## Troubleshooting

### Connection Issues

**Problem**: `Failed to connect to Kraken`

**Solutions**:
1. Check internet connection
2. Verify API credentials in `.env`
3. Ensure API key has correct permissions
4. Check Kraken API status: https://status.kraken.com/

---

### Authentication Errors

**Problem**: `Invalid signature` or `Invalid nonce`

**Solutions**:
1. Verify `KRAKEN_API_SECRET` is the **Private Key** from Kraken (not API Key)
2. Set Nonce Window to `888888888` in Kraken API settings
3. Check system time is synchronized
4. Regenerate API keys if needed

---

### Not Enough Data

**Problem**: `Collecting data... (35/50)`

**Solution**: This is normal! Bot needs 50+ data points before analysis.
- Wait ~15-30 minutes for data collection
- Bot checks market every 30 seconds by default

---

### No Signals Generated

**Problem**: Bot analyzes but never generates buy/sell signals

**Solutions**:
1. **Normal Behavior**: Some strategies wait for specific conditions
2. **Check Strategy**: Read the strategy's requirements (see Understanding Strategies)
3. **Review Logs**: Look for "Signal: None" and reasons
4. **Market Conditions**: Some markets don't offer good entry points

---

### Rate Limit Errors

**Problem**: `Rate limit exceeded`

**Solutions**:
1. Increase `API_CALL_DELAY`:
   ```bash
   API_CALL_DELAY=3.0  # Slow down API calls
```
2. Reduce number of coins in multi-coin mode
3. Check Kraken account tier (higher tiers = more API calls)

---

### Strategy Not Switching

**Problem**: Market changed but strategy didn't switch

**Expected Behavior**:
- Requires **3 confirmations** (90 minutes)
- **1-hour cooldown** after last switch
- **Max 4 switches per day**

**Check Logs**:
```bash
grep "Confirmation" logs/adaptive_bot.log
grep "SWITCHING" logs/adaptive_bot.log
```

---

### Position Size Too Small

**Problem**: Orders rejected as too small

**Solutions**:
1. Increase order sizes in `.env`:
   ```bash
   XBTUSD_ORDER_SIZE=0.002  # Increase from 0.001
```
2. Check Kraken minimum order sizes
3. Ensure sufficient account balance

---

### File Not Found Errors

**Problem**: `FileNotFoundError: .env`

**Solutions**:
1. Create `.env` from template:
   ```bash
   cp .env.example .env
```
2. Run from correct directory:
   ```bash
   cd src  # Must be in src/ directory
```

---

## Advanced Usage

### Custom Per-Coin Settings

Set different parameters for each coin:

```bash
# Different max positions
XBTUSD_MAX_POSITION_PCT=30   # BTC can be 30% of portfolio
SOLUSD_MAX_POSITION_PCT=20   # SOL max 20%
ETHUSD_MAX_POSITION_PCT=15   # ETH max 15%
XMRUSD_MAX_POSITION_PCT=15   # XMR max 15%

# Different order sizes
XBTUSD_ORDER_SIZE=0.001
SOLUSD_ORDER_SIZE=0.5
ETHUSD_ORDER_SIZE=0.05
XMRUSD_ORDER_SIZE=0.2
```

---

### Tuning Strategy Parameters

#### Mean Reversion (BTC $94k-$106k Range)

```bash
# Adjust for current BTC range
SUPPORT_LEVEL=95000      # Lower bound
RESISTANCE_LEVEL=103000  # Upper bound
SUPPORT_ZONE=2000        # Tolerance
RESISTANCE_ZONE=2000

# RSI sensitivity
RSI_OVERSOLD=35          # More aggressive (lower = more buys)
RSI_OVERBOUGHT=65        # More aggressive (higher = more sells)
```

#### SMA Crossover (Trending Markets)

```bash
# Faster signals (more trades)
FAST_SMA_PERIOD=5
SLOW_SMA_PERIOD=20

# Slower signals (fewer trades, less noise)
FAST_SMA_PERIOD=20
SLOW_SMA_PERIOD=50
```

#### Breakout Strategy

```bash
# More sensitive (detects smaller breakouts)
ATR_MULTIPLIER=1.0
VOLUME_THRESHOLD=1.3

# Less sensitive (only major breakouts)
ATR_MULTIPLIER=2.0
VOLUME_THRESHOLD=2.0
```

---

### Backtesting (Coming Soon)

The architecture supports backtesting, but it's not yet implemented. Structure:

```python
# Future feature
from backtesting import Backtester

backtester = Backtester(strategy='adaptive')
results = backtester.run(
    start_date='2024-01-01',
    end_date='2024-12-31',
    initial_balance=10000
)
print(results.summary())
```

---

### Running as a Service

#### Using systemd (Linux)

1. Create service file `/etc/systemd/system/spicetrader.service`:

```ini
[Unit]
Description=SpiceTrader Adaptive Bot
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/mnt/Unraid/Repo/spicetrader/src
ExecStart=/mnt/Unraid/Repo/spicetrader/venv/bin/python multi_coin_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

2. Enable and start:
```bash
sudo systemctl enable spicetrader
sudo systemctl start spicetrader
sudo systemctl status spicetrader
```

3. View logs:
```bash
sudo journalctl -u spicetrader -f
```

---

### Docker Deployment

Docker deployment is supported via `docker-compose.yml`.

- See `DOCKER.md` for setup and operations
- The container runs as a non-root user (UID `10001`); make sure `./logs` and `./data` are writable by UID `10001`

---

## Project Structure

```plaintext
spicetrader/
├── DOCKER.md
├── Dockerfile
├── docker-compose.yml
├── src/
│   ├── kraken/
│   │   ├── __init__.py
│   │   └── client.py              # Kraken API wrapper
│   ├── market_data.py             # OHLC cache + parsing helpers
│   ├── strategies/
│   │   ├── __init__.py
│   │   ├── base.py                # Strategy base class
│   │   ├── mean_reversion.py      # Range-bound strategy
│   │   ├── sma_crossover.py       # Trend following
│   │   ├── macd.py                # Moderate trends
│   │   ├── breakout.py            # Volatile breakouts
│   │   └── grid_trading.py        # Low volatility
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── market_analyzer.py     # Market state detection
│   │   ├── market_condition.py    # Market state data classes
│   │   └── strategy_selector.py   # Strategy selection logic
│   ├── indicators.py              # Technical indicators
│   ├── coin_trader.py             # Single-coin trader manager
│   ├── adaptive_bot.py            # Single-coin adaptive bot
│   ├── multi_coin_bot.py          # Multi-coin orchestrator
│   └── (legacy bot removed)        # src/bot.py was removed (use adaptive_bot.py)
├── scripts/
│   └── verify_dry_run.py          # Safety helper
├── tests/                         # Unit tests
├── logs/                          # Log files
├── data/                          # SQLite DB (runtime)
├── .env                           # Your configuration (create from .env.example)
├── .env.example                   # Configuration template
├── requirements.txt               # Python dependencies
└── README.md                      # This file
```

---

## API Reference

### Kraken Client

```python
from src.kraken.client import KrakenClient

# Initialize
client = KrakenClient(api_key, api_secret)

# Public endpoints
server_time = client.get_server_time()
ticker = client.get_ticker('XBTUSD')
ohlc = client.get_ohlc('XBTUSD', interval=5)
order_book = client.get_order_book('XBTUSD')
trades = client.get_recent_trades('XBTUSD')

# Private endpoints
balance = client.get_account_balance()
trade_balance = client.get_trade_balance()
open_orders = client.get_open_orders()

# Place orders
result = client.add_order(
    pair='XBTUSD',
    type='buy',
    ordertype='limit',
    volume=0.001,
    price=50000.0,
    validate=True  # Dry-run
)

# Cancel orders
client.cancel_order(txid='ORDER-ID')
client.cancel_all_orders()
```

### Indicators

```python
from src.indicators import *

# Trend indicators
rsi = calculate_rsi(prices, period=14)
macd_line, signal_line, histogram = calculate_macd(prices)
adx = calculate_adx(highs, lows, closes, period=14)

# Volatility
atr = calculate_atr(highs, lows, closes, period=14)
upper_bb, middle_bb, lower_bb = calculate_bollinger_bands(prices)

# Market classification
choppiness = calculate_choppiness_index(highs, lows, closes)
slope = calculate_linear_regression_slope(prices)
```

### Strategy Base Class

```python
from strategies.base import TradingStrategy

class MyStrategy(TradingStrategy):
    def analyze(self, market_data):
        # Your logic
        if should_buy:
            return 'buy'
        elif should_sell:
            return 'sell'
        return None
```

---

## Resources

- [Kraken API Documentation](https://docs.kraken.com/api/)
- [Kraken API Rate Limits](https://docs.kraken.com/api/docs/guides/spot-rest-ratelimits/)
- [Kraken Support](https://support.kraken.com/)
- [Technical Analysis Library](https://github.com/bukosabino/ta)
- [ADAPTIVE_TRADING_GUIDE.md](ADAPTIVE_TRADING_GUIDE.md) - Detailed strategy guide

---

## Disclaimer

**IMPORTANT - READ CAREFULLY**

This software is provided for **educational and research purposes only**.

### Risks

- Cryptocurrency trading carries **substantial risk**
- You can **lose all your invested capital**
- Past performance does **not guarantee future results**
- Automated trading can **amplify losses**
- Market conditions change; strategies may stop working

### No Warranty

This software is provided "as is" without warranty of any kind. The authors are not responsible for any losses incurred through use of this software.

### Recommendations

1. **Test Thoroughly**: Run in dry-run mode for at least 1 week
2. **Start Small**: Begin with minimum position sizes
3. **Monitor Actively**: Watch the bot closely for the first few days
4. **Understand Risks**: Only trade with funds you can afford to lose
5. **Stay Informed**: Keep up with market news and conditions
6. **Have Exit Plans**: Know when to stop the bot

### Legal

- You are responsible for complying with all applicable laws and regulations
- You are responsible for all tax obligations
- API keys are your responsibility to secure
- The authors assume no liability for your trading decisions

**By using this software, you acknowledge and accept all risks.**

---

## License

MIT License

Copyright (c) 2025 SpiceTrader

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

---

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

---

## Support

- **Issues**: Report bugs or request features via GitHub Issues
- **Discussions**: Join community discussions
- **Documentation**: See ADAPTIVE_TRADING_GUIDE.md for detailed strategy info

---

**Happy Trading! 🚀**

*Remember: Test thoroughly, start small, and never risk more than you can afford to lose.*
