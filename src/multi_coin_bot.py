"""Multi-Coin Adaptive Trading Bot."""
import os
import time
import logging
from typing import Dict, List, Optional
from datetime import datetime
from dotenv import load_dotenv

from .kraken.client import KrakenClient
from .coin_trader import CoinTrader
from .database import TradingDatabase
from .market_data import OHLCCache
from .position_sizing import equal_split_quote_allocation

# Configure logging
import pathlib
log_dir = pathlib.Path(__file__).parent.parent / 'logs'
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_dir / 'multi_coin_bot.log')
    ]
)
logger = logging.getLogger(__name__)


class MultiCoinBot:
    """
    Multi-coin adaptive trading bot.

    Manages multiple CoinTraders, each trading a different cryptocurrency
    with independent strategy selection and market analysis.
    """

    def __init__(self, api_key: str, api_secret: str, config: dict):
        """
        Initialize multi-coin bot.

        Args:
            api_key: Kraken API key
            api_secret: Kraken API secret
            config: Bot configuration
        """
        self.client = KrakenClient(api_key, api_secret)
        self.config = config
        self.running = False

        # Parse trading pairs
        trading_pairs_str = config.get('TRADING_PAIRS', 'XBTUSD')
        self.trading_pairs = [pair.strip() for pair in trading_pairs_str.split(',')]

        # Bot settings
        self.dry_run = config.get('DRY_RUN', 'true').lower() == 'true'
        self.api_call_delay = float(config.get('API_CALL_DELAY', 2.0))

        # Position sizing
        self.max_total_exposure = float(config.get('MAX_TOTAL_EXPOSURE', 75.0))  # % of account
        self.max_per_coin = float(config.get('MAX_PER_COIN', 25.0))  # % of account
        self.position_sizing_mode = str(config.get('POSITION_SIZING_MODE', 'pct')).strip().lower()
        self.fee_buffer_pct = float(config.get('FEE_BUFFER_PCT', 1.0))

        # OHLC settings (used for indicator correctness)
        self.ohlc_interval = int(config.get('OHLC_INTERVAL', 1))
        self.ohlc_cache = OHLCCache(interval=self.ohlc_interval, maxlen=200)

        # Initialize database
        self.db = TradingDatabase()

        # Create CoinTraders
        self.traders: Dict[str, CoinTrader] = {}
        for pair in self.trading_pairs:
            self.traders[pair] = CoinTrader(pair, config, db=self.db)

        # Account state
        self.account_balance = 0.0
        self.total_exposure = 0.0
        self.last_balance_log = time.time()

        print("\n" + "=" * 80)
        print("MULTI-COIN ADAPTIVE TRADING BOT")
        print("=" * 80)
        print(f"Trading Pairs: {', '.join(self.trading_pairs)}")
        print(f"Dry Run: {self.dry_run}")
        print(f"Max Total Exposure: {self.max_total_exposure}%")
        print(f"Max Per Coin: {self.max_per_coin}%")
        print(f"Position Sizing Mode: {self.position_sizing_mode}")
        print(f"Fee Buffer: {self.fee_buffer_pct}%")
        print("=" * 80 + "\n")

    def check_connection(self) -> bool:
        """Check connection to Kraken."""
        try:
            self.client.get_server_time()
            logger.info(f"✓ Connected to Kraken")
            return True
        except Exception as e:
            logger.error(f"✗ Connection failed: {e}")
            return False

    def update_account_balance(self) -> bool:
        """Update account balance."""
        try:
            trade_balance = self.client.get_trade_balance()
            self.account_balance = float(trade_balance.get('eb', 0))

            # Log balance only every 60 seconds to reduce verbosity
            current_time = time.time()
            if current_time - self.last_balance_log >= 60:
                logger.info(f"Account Balance: ${self.account_balance:,.2f}")
                self.last_balance_log = current_time

            return True
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return False

    def get_market_data(self, symbol: str) -> Optional[dict]:
        """Get market data for a symbol."""
        try:
            ticker = self.client.get_ticker(symbol)
            # Enrich with committed OHLC series for indicator/strategy calculations.
            try:
                self.ohlc_cache.update(self.client, symbol)
            except Exception as e:
                logger.debug(f"[{symbol}] OHLC update failed: {e}")

            return {
                'ticker': ticker,
                'ohlc': self.ohlc_cache.get_series(symbol),
                'timestamp': time.time()
            }
        except Exception as e:
            logger.error(f"[{symbol}] Failed to get market data: {e}")
            return None

    def get_all_market_data(self) -> Optional[Dict[str, dict]]:
        """Fetch market data for all symbols in one batch request."""
        try:
            # Fetch ticker data for all trading pairs at once
            pair_string = ','.join(self.trading_pairs)
            ticker_data = self.client.get_ticker(pair_string)
            timestamp = time.time()

            # Debug: log what Kraken returned
            logger.debug(f"Kraken batch response keys: {list(ticker_data.keys())}")

            # Build result mapping, handling Kraken's pair naming variations
            result = {}
            for symbol in self.trading_pairs:
                # Best-effort OHLC enrichment (OHLC cannot be fetched in a single batch call).
                try:
                    self.ohlc_cache.update(self.client, symbol)
                except Exception as e:
                    logger.debug(f"[{symbol}] OHLC update failed (batch): {e}")

                # Try exact match first, then try Kraken variations
                key = symbol
                if symbol not in ticker_data:
                    # Try common Kraken variations
                    variations = [
                        symbol.replace('XBT', 'XXBT').replace('USD', 'ZUSD'),
                        symbol.replace('ETH', 'XETH').replace('USD', 'ZUSD'),
                        symbol.replace('XRP', 'XXRP').replace('USD', 'ZUSD'),
                        symbol.replace('XMR', 'XXMR').replace('USD', 'ZUSD'),
                    ]
                    for variation in variations:
                        if variation in ticker_data:
                            key = variation
                            break

                # Only include if we found data
                if key in ticker_data:
                    result[symbol] = {
                        'ticker': {key: ticker_data[key]},
                        'ohlc': self.ohlc_cache.get_series(symbol),
                        'timestamp': timestamp,
                    }
                else:
                    logger.warning(f"[{symbol}] Not found in Kraken response (tried: {symbol}, {variations})")

            if not result:
                logger.error(f"No symbols found in Kraken response. Available: {list(ticker_data.keys())}")
                return None

            return result
        except Exception as e:
            logger.error(f"Failed to get batch market data: {e}")
            return None

    def calculate_position_size(self, symbol: str, current_price: float) -> float:
        """
        Calculate appropriate position size for a symbol.

        Args:
            symbol: Trading pair
            current_price: Current price

        Returns:
            Position size in base currency
        """
        # Get trader config
        trader = self.traders.get(symbol)
        if not trader:
            return 0.0

        # Calculate max position value for this coin.
        max_coin_value = (self.account_balance * trader.max_position_pct) / 100

        # Optionally use equal-split sizing based on account balance.
        if self.position_sizing_mode in {"equal", "equal_split", "per_coin", "dynamic"}:
            per_coin_value = equal_split_quote_allocation(
                self.account_balance,
                len(self.trading_pairs),
                fee_buffer_pct=self.fee_buffer_pct,
                exposure_pct=self.max_total_exposure,
            )
            position_value = min(max_coin_value, per_coin_value)
        else:
            # Default: percentage-based sizing.
            remaining_exposure = self.max_total_exposure - self.total_exposure
            if remaining_exposure <= 0:
                logger.warning(f"[{symbol}] Max total exposure reached ({self.total_exposure:.1f}%)")
                return 0.0

            available_pct = min(trader.max_position_pct, remaining_exposure)
            available_value = (self.account_balance * available_pct) / 100

            # Use the smaller of the two limits
            position_value = min(max_coin_value, available_value)

        # Convert to base currency amount
        if current_price > 0:
            position_size = position_value / current_price
        else:
            position_size = 0.0

        return position_size

    def place_order(self, symbol: str, order_type: str, size: float, price: Optional[float] = None) -> tuple:
        """
        Place an order.

        Returns:
            Tuple of (success: bool, txid: str)
        """
        try:
            ordertype = 'limit' if price else 'market'

            if self.dry_run:
                logger.info(f"[{symbol}] [🔸 DRY RUN] {order_type.upper()} {ordertype}: {size:.6f} @ ${price or 'market'} (dry_run=True)")
                return True, None

            logger.info(f"[{symbol}] [⚠️  LIVE] Placing {order_type.upper()} {ordertype}: {size:.6f} @ ${price or 'market'} (dry_run=False)")

            # Normalize/validate against Kraken AssetPairs rules.
            volume_norm, price_norm = self.client.normalize_order(
                pair=symbol,
                ordertype=ordertype,
                volume=size,
                price=price,
                current_price=price,
            )
            result = self.client.add_order(
                pair=symbol,
                type=order_type,
                ordertype=ordertype,
                volume=volume_norm,
                price=price_norm,
                validate=False
            )

            # Extract transaction ID
            txid = None
            if result and 'txid' in result:
                txid = result['txid'][0] if isinstance(result['txid'], list) else result['txid']

            logger.info(f"[{symbol}] Order placed: {result}")
            return True, txid

        except Exception as e:
            logger.error(f"[{symbol}] Order failed: {e}")
            return False, None

    def run_iteration(self):
        """Run one iteration of the multi-coin bot."""
        print("\n" + "=" * 80)
        print(f"ITERATION - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)

        # Update account balance
        self.update_account_balance()

        # Track signals
        signals = {}

        # Fetch all market data in single batch request
        all_market_data = self.get_all_market_data()
        if not all_market_data:
            logger.warning("Failed to fetch market data")
            return

        # Analyze each coin
        for symbol, trader in self.traders.items():
            print(f"\n--- {symbol} ---")

            # Get market data from batch
            market_data = all_market_data.get(symbol)
            if not market_data:
                logger.warning(f"[{symbol}] No market data in batch")
                continue

            # Get trading signal
            signal = trader.analyze(market_data)

            if signal:
                signals[symbol] = signal
                logger.info(f"[{symbol}] 📊 Signal: {signal.upper()}")

        # Execute signals with position sizing
        if signals:
            logger.info(f"\n🎯 Executing {len(signals)} signal(s)...")

            for symbol, signal in signals.items():
                trader = self.traders[symbol]

                # Check if already acted on this signal
                if trader.current_strategy and signal == trader.current_strategy.last_signal:
                    logger.info(f"[{symbol}] Signal already acted upon, skipping")
                    continue

                # Get current price
                market_data = self.get_market_data(symbol)
                if not market_data:
                    continue

                ticker_data = market_data['ticker']
                pair_key = trader._find_pair_key(ticker_data)
                if not pair_key:
                    continue

                current_price = float(ticker_data[pair_key]['c'][0])

                # Enforce spot-style position management: one open position per symbol.
                # Use DB as source of truth so restarts don't strand open positions.
                open_position = None
                if self.db:
                    try:
                        open_position = self.db.get_open_position(symbol)
                    except Exception as e:
                        logger.warning(f"[{symbol}] Failed to fetch open position from DB: {e}")

                # Calculate position size
                position_size = self.calculate_position_size(symbol, current_price)

                if position_size > 0:
                    if signal == 'buy' and open_position:
                        logger.info(f"[{symbol}] Skipping BUY - already have open position (id={open_position.get('id')})")
                        continue

                    if signal == 'sell' and not open_position:
                        logger.info(f"[{symbol}] Skipping SELL - no open position (spot mode; not opening shorts)")
                        continue

                    # MACD-only exit gating (prevents fee-churn exits on tiny moves).
                    if signal == 'sell' and open_position and str(open_position.get('strategy', '')).lower() == 'macd':
                        try:
                            entry_price = float(open_position['entry_price'])
                            entry_time = open_position.get('entry_time')
                            if isinstance(entry_time, str):
                                try:
                                    entry_dt = datetime.fromisoformat(entry_time)
                                except ValueError:
                                    entry_dt = None
                            else:
                                entry_dt = entry_time

                            hold_seconds = (datetime.now() - entry_dt).total_seconds() if entry_dt else None
                            gross_profit_pct = (current_price - entry_price) / entry_price
                            taker_fee = float(self.config.get('TAKER_FEE', 0.0026))
                            net_profit_pct = gross_profit_pct - (2.0 * taker_fee)

                            min_hold_time = int(self.config.get('MIN_HOLD_TIME', 900))
                            min_profit_target = float(self.config.get('MIN_PROFIT_TARGET', 0.010))

                            # Only gate *profitable* exits. Allow loss-cut exits immediately.
                            if net_profit_pct > 0:
                                if hold_seconds is not None and hold_seconds < min_hold_time:
                                    logger.info(
                                        f"[{symbol}] MACD SELL gated (hold {int(hold_seconds)}s < {min_hold_time}s). "
                                        f"net={net_profit_pct*100:.2f}%"
                                    )
                                    continue

                                if net_profit_pct < min_profit_target:
                                    logger.info(
                                        f"[{symbol}] MACD SELL gated (net {net_profit_pct*100:.2f}% < target {min_profit_target*100:.2f}%)."
                                    )
                                    continue
                        except Exception as e:
                            logger.warning(f"[{symbol}] MACD gating check failed, proceeding: {e}")

                    # Place order
                    success, txid = self.place_order(symbol, signal, position_size, current_price)

                    if success and trader.current_strategy:
                        # Get actual fee from Kraken if not in dry run
                        actual_fee = 0.0
                        if not self.dry_run and txid:
                            logger.info(f"[{symbol}] Fetching actual fee for txid: {txid}")
                            actual_fee = self.client.get_trade_actual_fee(txid, max_wait_seconds=10)
                            if actual_fee > 0:
                                logger.info(f"[{symbol}] Actual fee retrieved: ${actual_fee:.2f}")

                        # Record entry/exit for fee + DB tracking.
                        if signal == 'buy':
                            trader.record_entry(current_price, position_size, fee=actual_fee, dry_run=self.dry_run)
                            trader.current_strategy.update_position('long')
                        else:  # sell
                            trader.record_exit(current_price, position_size, fee=actual_fee, dry_run=self.dry_run)
                            trader.current_strategy.update_position(None)

                        trader.current_strategy.update_signal(signal)
                        trader.total_trades += 1

                        logger.info(f"[{symbol}] ✅ {signal.upper()} executed: {position_size:.6f} @ ${current_price:,.2f}")

        # Display summary
        self._display_summary()

        print("=" * 80)

    def _display_summary(self):
        """Display trading summary for all coins."""
        print(f"\n📊 PORTFOLIO SUMMARY")
        print("-" * 80)

        total_fees = 0.0
        total_net_pnl = 0.0
        total_gross_pnl = 0.0

        for symbol, trader in self.traders.items():
            stats = trader.get_stats()
            print(
                f"{symbol:10s} | {stats['strategy']:15s} | {stats['market_state']:20s} | "
                f"Pos: {stats['position'] or 'None':6s} | Trades: {stats['total_trades']}"
            )

            # Accumulate totals
            if trader.track_fees:
                total_fees += trader.cumulative_fees
                total_net_pnl += trader.net_pnl
                total_gross_pnl += trader.gross_pnl

        print("-" * 80)

        # Display fee summary if tracking
        if any(t.track_fees for t in self.traders.values()):
            print(
                f"💰 Total Fees: ${total_fees:.2f} | "
                f"Gross P&L: ${total_gross_pnl:.2f} | "
                f"Net P&L: ${total_net_pnl:.2f}"
            )
            print("-" * 80)

    def start(self):
        """Start the multi-coin bot."""
        logger.info("Starting Multi-Coin Adaptive Bot...")

        # Display dry run configuration
        logger.info("=" * 80)
        logger.info("DRY RUN CONFIGURATION")
        logger.info("=" * 80)
        logger.info(f"Environment Variable DRY_RUN: {os.getenv('DRY_RUN', 'true')}")
        logger.info(f"Bot dry_run setting: {self.dry_run}")
        if self.dry_run:
            logger.info("Mode: 🔸 DRY RUN MODE - NO REAL TRADES WILL BE EXECUTED")
        else:
            logger.warning("Mode: ⚠️  LIVE TRADING MODE - REAL MONEY AT RISK")
            logger.warning("⚠️  You have 5 seconds to cancel (Ctrl+C)...")
            time.sleep(5)
        logger.info("=" * 80)

        # Check connection
        if not self.check_connection():
            logger.error("Failed to connect. Exiting.")
            return

        # Update balance
        if not self.update_account_balance():
            logger.error("Failed to get account balance. Exiting.")
            return

        self.running = True
        logger.info("✓ Bot is running. Press Ctrl+C to stop.\n")

        try:
            while self.running:
                self.run_iteration()
                time.sleep(self.api_call_delay)

        except KeyboardInterrupt:
            logger.info("\nReceived stop signal...")
            self.stop()

    def stop(self):
        """Stop the bot."""
        logger.info("Stopping Multi-Coin Bot...")
        self.running = False

        # Display final summary
        logger.info("\n" + "=" * 80)
        logger.info("FINAL SUMMARY")
        logger.info("=" * 80)
        self._display_summary()

        logger.info("Bot stopped")


def main():
    """Main entry point."""
    load_dotenv()

    api_key = os.getenv('KRAKEN_API_KEY')
    api_secret = os.getenv('KRAKEN_API_SECRET')

    if not api_key or not api_secret:
        logger.error("API credentials not found")
        raise SystemExit(1)

    # Load configuration
    config = {
        'TRADING_PAIRS': os.getenv('TRADING_PAIRS', 'XBTUSD,ETHUSD,SOLUSD,XRPUSD'),
        'DRY_RUN': os.getenv('DRY_RUN', 'true'),
        'API_CALL_DELAY': os.getenv('API_CALL_DELAY', '3.0'),  # Safe for Starter tier with 4 coins

        # Position sizing
        'MAX_TOTAL_EXPOSURE': os.getenv('MAX_TOTAL_EXPOSURE', '75'),
        'MAX_PER_COIN': os.getenv('MAX_PER_COIN', '25'),
        'POSITION_SIZING_MODE': os.getenv('POSITION_SIZING_MODE', 'equal'),
        'FEE_BUFFER_PCT': os.getenv('FEE_BUFFER_PCT', '1.0'),

        # Per-coin order sizes (Optimized for profit)
        'XBTUSD_ORDER_SIZE': os.getenv('XBTUSD_ORDER_SIZE', '0.0002'),
        'ETHUSD_ORDER_SIZE': os.getenv('ETHUSD_ORDER_SIZE', '0.02'),
        'SOLUSD_ORDER_SIZE': os.getenv('SOLUSD_ORDER_SIZE', '0.2'),
        'XRPUSD_ORDER_SIZE': os.getenv('XRPUSD_ORDER_SIZE', '75.0'),

        # Adaptive settings (shared across all coins)
        'REANALYSIS_INTERVAL': os.getenv('REANALYSIS_INTERVAL', '3600'),
        'SWITCH_COOLDOWN': os.getenv('SWITCH_COOLDOWN', '3600'),
        'CONFIRMATIONS_REQUIRED': os.getenv('CONFIRMATIONS_REQUIRED', '3'),
        'MAX_SWITCHES_PER_DAY': os.getenv('MAX_SWITCHES_PER_DAY', '4'),

        # Market analyzer settings
        'ADX_STRONG_TREND': os.getenv('ADX_STRONG_TREND', '25'),
        'ADX_WEAK_TREND': os.getenv('ADX_WEAK_TREND', '20'),
        'CHOPPINESS_CHOPPY': os.getenv('CHOPPINESS_CHOPPY', '61.8'),
        'CHOPPINESS_TRENDING': os.getenv('CHOPPINESS_TRENDING', '38.2'),
        'RANGE_TIGHT': os.getenv('RANGE_TIGHT', '5'),
        'RANGE_MODERATE': os.getenv('RANGE_MODERATE', '15'),

        # Strategy parameters
        'RSI_PERIOD': os.getenv('RSI_PERIOD', '14'),
        'RSI_OVERSOLD': os.getenv('RSI_OVERSOLD', '40'),
        'RSI_OVERBOUGHT': os.getenv('RSI_OVERBOUGHT', '60'),
        'BB_PERIOD': os.getenv('BB_PERIOD', '20'),
        'BB_STD_DEV': os.getenv('BB_STD_DEV', '2.0'),
        'FAST_SMA_PERIOD': os.getenv('FAST_SMA_PERIOD', '10'),
        'SLOW_SMA_PERIOD': os.getenv('SLOW_SMA_PERIOD', '30'),
        'MACD_FAST': os.getenv('MACD_FAST', '12'),
        'MACD_SLOW': os.getenv('MACD_SLOW', '26'),
        'MACD_SIGNAL': os.getenv('MACD_SIGNAL', '9'),

        # Risk / exit behavior (used by multiple strategies)
        'MIN_PROFIT_TARGET': os.getenv('MIN_PROFIT_TARGET', '0.010'),
        'MIN_HOLD_TIME': os.getenv('MIN_HOLD_TIME', '900'),

        # Fee accounting
        'MAKER_FEE': os.getenv('MAKER_FEE', '0.0016'),
        'TAKER_FEE': os.getenv('TAKER_FEE', '0.0026'),
        'TRACK_FEES': os.getenv('TRACK_FEES', 'true'),
        'MIN_PROFIT_PERCENT': os.getenv('MIN_PROFIT_PERCENT', '0.005'),
        'SKIP_UNPROFITABLE_TRADES': os.getenv('SKIP_UNPROFITABLE_TRADES', 'true'),
    }

    # Create and start bot
    bot = MultiCoinBot(api_key, api_secret, config)
    bot.start()


if __name__ == '__main__':
    main()
