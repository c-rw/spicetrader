"""Adaptive trading bot that automatically selects and switches strategies."""
import os
import time
import logging
from typing import Optional
from datetime import datetime, timedelta
from collections import deque
from dotenv import load_dotenv

from .kraken.client import KrakenClient
from .market_data import OHLCCache
from .analysis import MarketAnalyzer, StrategySelector, MarketCondition, MarketState
from .fee_calculator import FeeCalculator
from .database import TradingDatabase
from .position_sizing import equal_split_quote_allocation
from .config_utils import ConfigError, require, require_bool, require_float, require_int

# Configure logging
import pathlib
log_dir = pathlib.Path(__file__).parent.parent / 'logs'
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_dir / 'adaptive_bot.log')
    ]
)
logger = logging.getLogger(__name__)


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not str(value).strip():
        logger.error(
            f"Missing required environment variable: {name}. "
            "Set it in your .env (or Docker Compose env_file) and restart."
        )
        raise SystemExit(1)
    return value


class AdaptiveBot:
    """
    Adaptive trading bot with automatic strategy selection and switching.

    This bot analyzes market conditions and automatically selects the best
    strategy, switching when conditions change significantly.
    """

    def __init__(self, api_key: str, api_secret: str, config: dict):
        """
        Initialize adaptive trading bot.

        Args:
            api_key: Kraken API key
            api_secret: Kraken API secret
            config: Bot configuration dictionary
        """
        self.client = KrakenClient(api_key, api_secret)
        self.config = config
        self.running = False

        # Extract configuration
        self.trading_pair = str(require(config, 'TRADING_PAIR')).strip()
        self.order_size = require_float(config, 'ORDER_SIZE')
        self.position_sizing_mode = str(require(config, 'POSITION_SIZING_MODE')).strip().lower()
        self.fee_buffer_pct = require_float(config, 'FEE_BUFFER_PCT')
        self.max_total_exposure = require_float(config, 'MAX_TOTAL_EXPOSURE')
        self.dry_run = require_bool(config, 'DRY_RUN')
        self.api_call_delay = require_float(config, 'API_CALL_DELAY')

        # OHLC settings (used for indicator correctness)
        self.ohlc_interval = require_int(config, 'OHLC_INTERVAL')
        self.ohlc_cache = OHLCCache(interval=self.ohlc_interval, maxlen=200)

        # Adaptive settings
        self.reanalysis_interval = require_int(config, 'REANALYSIS_INTERVAL')
        self.switch_cooldown = require_int(config, 'SWITCH_COOLDOWN')
        self.confirmations_required = require_int(config, 'CONFIRMATIONS_REQUIRED')
        self.max_switches_per_day = require_int(config, 'MAX_SWITCHES_PER_DAY')

        # Initialize analyzer and selector
        self.analyzer = MarketAnalyzer(config)
        self.selector = StrategySelector(config)

        # Initialize database
        self.db = TradingDatabase()
        self.entry_price = None
        self.entry_fee = None
        self.exit_fee = None
        self.entry_volume = None
        self.current_position_id = None

        # Account state (quote-currency trade balance, e.g., USD)
        self.account_balance = 0.0
        self.last_balance_log = time.time()

        # Current state
        self.current_strategy = None
        self.current_market_condition = None
        self.last_analysis_time = None
        self.last_switch_time = None

        # Tracking for confirmation system
        self.pending_state = None
        self.pending_confirmations = 0

        # Daily switch counter
        self.switches_today = 0
        self.current_day = datetime.now().date()

        # Price history for analysis (bounded to prevent memory leaks)
        self.price_history = deque(maxlen=200)
        self.high_history = deque(maxlen=200)
        self.low_history = deque(maxlen=200)

        # Fee tracking
        self.fee_calculator = FeeCalculator(
            maker_fee=require_float(config, 'MAKER_FEE'),
            taker_fee=require_float(config, 'TAKER_FEE')
        )
        self.track_fees = require_bool(config, 'TRACK_FEES')
        self.cumulative_fees = 0.0
        self.total_trades = 0
        self.net_pnl = 0.0

        logger.info(f"Adaptive Bot initialized for {self.trading_pair}")
        logger.info(f"Dry run mode: {self.dry_run}")
        logger.info(f"Position sizing mode: {self.position_sizing_mode}")
        logger.info(f"Fee tracking: {self.track_fees}")
        logger.info(f"Re-analysis interval: {self.reanalysis_interval}s ({self.reanalysis_interval/60:.0f} min)")
        logger.info(f"Switch cooldown: {self.switch_cooldown}s ({self.switch_cooldown/60:.0f} min)")
        logger.info(f"Confirmations required: {self.confirmations_required}")
        logger.info(f"Max switches per day: {self.max_switches_per_day}")

    def check_connection(self) -> bool:
        """Check connection to Kraken API."""
        try:
            server_time = self.client.get_server_time()
            logger.info(f"Connected to Kraken. Server time: {server_time}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Kraken: {e}")
            return False

    def check_account(self) -> bool:
        """Check account access and balance."""
        try:
            balance = self.client.get_account_balance()
            logger.info(f"Account balance retrieved: {len(balance)} assets")

            trade_balance = self.client.get_trade_balance()
            logger.info(f"Trade balance: ${float(trade_balance.get('eb', 0)):,.2f}")

            # Cache for sizing (best-effort)
            try:
                self.account_balance = float(trade_balance.get('eb', 0))
            except Exception:
                self.account_balance = 0.0

            return True
        except Exception as e:
            logger.error(f"Failed to access account: {e}")
            return False

    def update_account_balance(self) -> bool:
        """Update cached quote balance used for sizing."""
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

    def _calculate_order_volume(self, price_estimate: Optional[float]) -> float:
        """Calculate order volume in base currency (e.g., BTC) for this pair."""
        if self.position_sizing_mode not in {"equal", "equal_split", "per_coin", "dynamic"}:
            return float(self.order_size)

        if not price_estimate or price_estimate <= 0:
            return float(self.order_size)

        # Single-coin bot => "divide by how many coins" is 1.
        per_coin_value = equal_split_quote_allocation(
            self.account_balance,
            1,
            fee_buffer_pct=self.fee_buffer_pct,
            exposure_pct=self.max_total_exposure,
        )
        if per_coin_value <= 0:
            return float(self.order_size)

        return per_coin_value / float(price_estimate)

    def get_market_data(self) -> Optional[dict]:
        """Get current market data."""
        try:
            ticker = self.client.get_ticker(self.trading_pair)
            order_book = self.client.get_order_book(self.trading_pair, count=10)

            try:
                self.ohlc_cache.update(self.client, self.trading_pair)
            except Exception as e:
                logger.debug(f"OHLC update failed: {e}")

            return {
                'ticker': ticker,
                'order_book': order_book,
                'ohlc': self.ohlc_cache.get_series(self.trading_pair),
                'timestamp': time.time()
            }
        except Exception as e:
            logger.error(f"Failed to get market data: {e}")
            return None

    def should_reanalyze(self) -> bool:
        """
        Check if it's time to re-analyze market conditions.

        Returns:
            True if re-analysis should be performed
        """
        if self.last_analysis_time is None:
            return True

        time_since_analysis = time.time() - self.last_analysis_time
        return time_since_analysis >= self.reanalysis_interval

    def can_switch_strategy(self) -> bool:
        """
        Check if strategy switching is allowed.

        Returns:
            True if switching is allowed
        """
        # Check daily limit
        today = datetime.now().date()
        if today != self.current_day:
            # New day, reset counter
            self.current_day = today
            self.switches_today = 0

        if self.switches_today >= self.max_switches_per_day:
            logger.warning(f"Daily switch limit reached ({self.switches_today}/{self.max_switches_per_day})")
            return False

        # Check cooldown
        if self.last_switch_time is None:
            return True

        time_since_switch = time.time() - self.last_switch_time
        if time_since_switch < self.switch_cooldown:
            remaining = self.switch_cooldown - time_since_switch
            logger.debug(f"Cooldown active: {remaining:.0f}s remaining")
            return False

        return True

    def analyze_and_update_strategy(self):
        """
        Analyze market and update strategy if needed.

        This implements the confirmation system to avoid excessive switching.
        """
        # Need enough data - check this first, before reanalysis interval
        min_required = self.analyzer.get_required_data_points()
        if len(self.price_history) < min_required:
            logger.info(f"Collecting data... ({len(self.price_history)}/{min_required})")
            # Don't update last_analysis_time - we want to check data collection every iteration
            return

        # Only enforce reanalysis interval after we have enough data
        if not self.should_reanalyze():
            return

        logger.info("=" * 80)
        logger.info("ANALYZING MARKET CONDITIONS")
        logger.info("=" * 80)

        # Analyze current market (convert deques to lists for slicing support in indicators)
        market_condition = self.analyzer.analyze(
            list(self.price_history),
            list(self.high_history),
            list(self.low_history)
        )

        self.current_market_condition = market_condition
        self.last_analysis_time = time.time()

        logger.info(f"📊 {market_condition}")
        logger.info(f"Description: {market_condition.description}")

        # Get recommended strategy
        recommended_strategy_name = market_condition.get_recommended_strategy()

        # If no current strategy, set it
        if self.current_strategy is None:
            logger.info(f"✅ Initial strategy selection: {recommended_strategy_name}")
            self.current_strategy = self.selector.select_strategy(market_condition)
            logger.info(f"Strategy: {self.current_strategy.get_strategy_name()}")
            return

        # Check if recommended strategy is different
        current_strategy_name = self._get_strategy_name(self.current_strategy)

        if recommended_strategy_name == current_strategy_name:
            # Same strategy, reset pending confirmations
            if self.pending_confirmations > 0:
                logger.info(f"Strategy confirmation reset (back to {current_strategy_name})")
            self.pending_state = None
            self.pending_confirmations = 0
            logger.info(f"✅ Continuing with {current_strategy_name}")
            return

        # Different strategy recommended
        logger.info(f"🔄 New strategy recommended: {recommended_strategy_name} (current: {current_strategy_name})")

        # Check if it's the same as pending
        if self.pending_state == market_condition.state:
            self.pending_confirmations += 1
            logger.info(f"Confirmation {self.pending_confirmations}/{self.confirmations_required} for {recommended_strategy_name}")
        else:
            # New pending state
            self.pending_state = market_condition.state
            self.pending_confirmations = 1
            logger.info(f"Starting confirmation process for {recommended_strategy_name} (1/{self.confirmations_required})")

        # Check if we have enough confirmations
        if self.pending_confirmations >= self.confirmations_required:
            if self.can_switch_strategy():
                self._switch_strategy(market_condition, recommended_strategy_name)
            else:
                logger.warning("Switch criteria met but cooldown/limits prevent switching")

    def _switch_strategy(self, market_condition: MarketCondition, new_strategy_name: str):
        """
        Switch to a new strategy.

        Args:
            market_condition: Current market condition
            new_strategy_name: Name of new strategy
        """
        old_strategy_name = self._get_strategy_name(self.current_strategy)

        logger.info("=" * 80)
        logger.info(f"🔄 SWITCHING STRATEGY")
        logger.info(f"From: {old_strategy_name}")
        logger.info(f"To: {new_strategy_name}")
        logger.info(f"Reason: {market_condition.description}")
        logger.info("=" * 80)

        # Close any open positions (conservative approach)
        if self.current_strategy and self.current_strategy.position:
            logger.warning(f"Closing {self.current_strategy.position} position before switch")
            # TODO: Implement position closing logic
            self.current_strategy.update_position(None)

        # Select new strategy
        self.current_strategy = self.selector.select_strategy(market_condition)

        # Update tracking
        self.last_switch_time = time.time()
        self.switches_today += 1
        self.pending_state = None
        self.pending_confirmations = 0

        logger.info(f"✅ Strategy switched successfully ({self.switches_today}/{self.max_switches_per_day} today)")
        logger.info(f"New strategy: {self.current_strategy.get_strategy_name()}")

    def _get_strategy_name(self, strategy) -> str:
        """Get strategy name from strategy instance."""
        if strategy is None:
            return "none"
        return strategy.__class__.__name__.replace('Strategy', '').lower().replace('sma', 'sma_').replace('crossover', 'crossover')

    def update_price_history(self, market_data: dict):
        """Update price history from market data. Deque automatically maintains max size."""
        ohlc = market_data.get('ohlc')
        if isinstance(ohlc, dict) and isinstance(ohlc.get('latest'), dict):
            latest = ohlc['latest']
            close = float(latest['close'])
            high = float(latest['high'])
            low = float(latest['low'])
        else:
            ticker_data = market_data.get('ticker', {})
            pair_key = self._get_pair_key(ticker_data)
            if not pair_key:
                return
            ticker = ticker_data[pair_key]
            close = float(ticker['c'][0])
            high = float(ticker['h'][0])
            low = float(ticker['l'][0])

        self.price_history.append(close)
        self.high_history.append(high)
        self.low_history.append(low)

    def _get_pair_key(self, ticker_data: dict) -> Optional[str]:
        """Find the actual trading pair key in ticker response."""
        if self.trading_pair in ticker_data:
            return self.trading_pair

        variations = [
            self.trading_pair,
            self.trading_pair.replace('XBT', 'XXBT').replace('USD', 'ZUSD'),
            self.trading_pair.replace('ETH', 'XETH').replace('USD', 'ZUSD'),
        ]

        for variation in variations:
            if variation in ticker_data:
                return variation

        if ticker_data:
            return list(ticker_data.keys())[0]

        return None

    def place_order(self, order_type: str, price: Optional[float] = None) -> Optional[dict]:
        """Place an order."""
        try:
            ordertype = 'limit' if price else 'market'

            # Estimate price for sizing/normalization.
            price_estimate = price
            if price_estimate is None and self.price_history:
                price_estimate = float(self.price_history[-1])

            volume = self._calculate_order_volume(price_estimate)

            if self.dry_run:
                logger.info(f"[🔸 DRY RUN] Would place {order_type} {ordertype} order: "
                          f"{volume} {self.trading_pair}" +
                          (f" @ ${price:,.2f}" if price else "") + " (dry_run=True)")
                return {
                    'dry_run': True,
                    'type': order_type,
                    'ordertype': ordertype,
                    'spice_volume': volume,
                }

            logger.info(f"[⚠️  LIVE] Placing {order_type} {ordertype} order: "
                      f"{volume} {self.trading_pair}" +
                      (f" @ ${price:,.2f}" if price else "") + " (dry_run=False)")

            # Normalize/validate against Kraken AssetPairs rules.
            volume_norm, price_norm = self.client.normalize_order(
                pair=self.trading_pair,
                ordertype=ordertype,
                volume=volume,
                price=price,
                current_price=price_estimate,
            )
            result = self.client.add_order(
                pair=self.trading_pair,
                type=order_type,
                ordertype=ordertype,
                volume=volume_norm,
                price=price_norm,
                validate=False
            )

            # Include normalized volume for downstream recording.
            try:
                result['spice_volume'] = float(volume_norm)
            except Exception:
                result['spice_volume'] = volume

            logger.info(f"Order placed: {result}")
            return result

        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            return None

    def record_entry(self, price: float, volume: float, fee: float = 0.0, dry_run: bool = True):
        """Record entry into a position."""
        self.entry_price = price
        self.entry_volume = volume
        self.entry_fee = fee if fee > 0 else self.fee_calculator.calculate_fee(price * volume)

        if self.track_fees:
            self.cumulative_fees += self.entry_fee
            self.total_trades += 1

        if self.db and self.current_strategy:
            position_type = self.current_strategy.position if self.current_strategy.position else 'long'
            strategy_name = self._get_strategy_name(self.current_strategy)
            market_state = self.current_market_condition.state.value if self.current_market_condition else None

            self.current_position_id = self.db.open_position(
                symbol=self.trading_pair,
                strategy=strategy_name,
                position_type=position_type,
                entry_price=price,
                entry_volume=volume,
                entry_fee=self.entry_fee,
                market_state=market_state,
                dry_run=dry_run
            )

            self.db.record_trade(
                symbol=self.trading_pair,
                strategy=strategy_name,
                trade_type='entry',
                side='buy' if position_type == 'long' else 'sell',
                price=price,
                volume=volume,
                fee=self.entry_fee,
                position_type=position_type,
                market_state=market_state,
                position_id=self.current_position_id,
                dry_run=dry_run
            )

    def record_exit(self, price: float, volume: float, fee: float = 0.0, dry_run: bool = True):
        """Record exit from a position and calculate P&L."""
        if self.entry_price is None:
            logger.warning("Exit recorded but no entry price!")
            return

        self.exit_fee = fee if fee > 0 else self.fee_calculator.calculate_fee(price * volume)

        position_type = 'long' if self.current_strategy and self.current_strategy.position == 'long' else 'short'
        gross_pnl, total_fees, net_pnl = self.fee_calculator.calculate_net_pnl(
            entry_price=self.entry_price,
            exit_price=price,
            volume=volume,
            position_type=position_type,
            entry_fee=self.entry_fee,
            exit_fee=self.exit_fee
        )

        self.net_pnl += net_pnl

        if self.track_fees:
            self.cumulative_fees += self.exit_fee

        if self.db and self.current_position_id:
            self.db.close_position(
                position_id=self.current_position_id,
                exit_price=price,
                exit_volume=volume,
                exit_fee=self.exit_fee
            )

            strategy_name = self._get_strategy_name(self.current_strategy) if self.current_strategy else 'unknown'
            market_state = self.current_market_condition.state.value if self.current_market_condition else None

            self.db.record_trade(
                symbol=self.trading_pair,
                strategy=strategy_name,
                trade_type='exit',
                side='sell' if position_type == 'long' else 'buy',
                price=price,
                volume=volume,
                fee=self.exit_fee,
                position_type=position_type,
                market_state=market_state,
                position_id=self.current_position_id,
                dry_run=dry_run
            )

            self.current_position_id = None

        self.entry_price = None
        self.entry_fee = None
        self.exit_fee = None
        self.entry_volume = None

    def run_strategy(self):
        """Execute current strategy."""
        logger.info("Running strategy iteration...")

        # Get market data
        market_data = self.get_market_data()
        if not market_data:
            return

        # Update cached balance once per iteration (best-effort).
        self.update_account_balance()

        # Update price history
        self.update_price_history(market_data)

        # Analyze and potentially switch strategy
        self.analyze_and_update_strategy()

        # If no strategy yet, wait
        if self.current_strategy is None:
            logger.info("No strategy selected yet, waiting for more data...")
            return

        # Run current strategy
        signal = self.current_strategy.analyze(market_data)

        # Execute trades based on signal
        if signal:
            if signal == self.current_strategy.last_signal:
                logger.info("Signal already acted upon, skipping...")
                return

            if signal == 'buy':
                if self.current_strategy.position == 'short':
                    # Get price for exit recording
                    market_data_fresh = self.get_market_data()
                    if market_data_fresh:
                        ticker_data = market_data_fresh['ticker']
                        pair_key = self._get_pair_key(ticker_data)
                        if pair_key:
                            current_price = float(ticker_data[pair_key]['c'][0])
                            self.record_exit(current_price, self.entry_volume or self.order_size, dry_run=self.dry_run)

                    logger.info("Closing short position before going long")
                    self.place_order('buy')

                logger.info("Opening long position")
                result = self.place_order('buy')
                if result:
                    used_volume = float(result.get('spice_volume', self.order_size))
                    # Get current price and record entry
                    market_data_fresh = self.get_market_data()
                    if market_data_fresh:
                        ticker_data = market_data_fresh['ticker']
                        pair_key = self._get_pair_key(ticker_data)
                        if pair_key:
                            current_price = float(ticker_data[pair_key]['c'][0])
                            self.record_entry(current_price, used_volume, dry_run=self.dry_run)

                    self.current_strategy.update_position('long')
                    self.current_strategy.update_signal('buy')

            elif signal == 'sell':
                if self.current_strategy.position == 'long':
                    # Get price for exit recording
                    market_data_fresh = self.get_market_data()
                    if market_data_fresh:
                        ticker_data = market_data_fresh['ticker']
                        pair_key = self._get_pair_key(ticker_data)
                        if pair_key:
                            current_price = float(ticker_data[pair_key]['c'][0])
                            self.record_exit(current_price, self.entry_volume or self.order_size, dry_run=self.dry_run)

                    logger.info("Closing long position before going short")
                    self.place_order('sell')

                logger.info("Opening short position")
                result = self.place_order('sell')
                if result:
                    used_volume = float(result.get('spice_volume', self.order_size))
                    # Get current price and record entry
                    market_data_fresh = self.get_market_data()
                    if market_data_fresh:
                        ticker_data = market_data_fresh['ticker']
                        pair_key = self._get_pair_key(ticker_data)
                        if pair_key:
                            current_price = float(ticker_data[pair_key]['c'][0])
                            self.record_entry(current_price, used_volume, dry_run=self.dry_run)

                    self.current_strategy.update_position('short')
                    self.current_strategy.update_signal('sell')

        logger.info("Strategy iteration complete")

    def start(self):
        """Start the adaptive trading bot."""
        logger.info("=" * 80)
        logger.info("STARTING ADAPTIVE TRADING BOT")
        logger.info("=" * 80)

        # Display dry run configuration
        logger.info("=" * 80)
        logger.info("DRY RUN CONFIGURATION")
        logger.info("=" * 80)
        logger.info(f"Environment Variable DRY_RUN: {os.getenv('DRY_RUN')}")
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

        # Check account
        if not self.check_account():
            logger.error("Failed to access account. Check API credentials.")
            return

        self.running = True
        logger.info("Bot is running. Press Ctrl+C to stop.")
        logger.info("=" * 80)

        try:
            while self.running:
                self.run_strategy()
                time.sleep(self.api_call_delay)

        except KeyboardInterrupt:
            logger.info("Received stop signal...")
            self.stop()

    def stop(self):
        """Stop the trading bot."""
        logger.info("Stopping adaptive trading bot...")
        self.running = False
        logger.info("Bot stopped")


def main():
    """Main entry point."""
    load_dotenv()

    # Get API credentials
    api_key = _require_env('KRAKEN_API_KEY')
    api_secret = _require_env('KRAKEN_API_SECRET')

    # Env-pass-through config: everything comes from environment.
    config = dict(os.environ)

    try:
        bot = AdaptiveBot(api_key, api_secret, config)
        bot.start()
    except ConfigError as e:
        logger.error(str(e))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
