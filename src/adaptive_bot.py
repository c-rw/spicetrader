"""Adaptive trading bot that automatically selects and switches strategies."""
import os
import sys
import time
import logging
from typing import Optional
from datetime import datetime, timedelta
from collections import deque
from dotenv import load_dotenv

from kraken.client import KrakenClient
from analysis import MarketAnalyzer, StrategySelector, MarketCondition, MarketState
from fee_calculator import FeeCalculator
from database import TradingDatabase

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
        self.trading_pair = config.get('TRADING_PAIR', 'XBTUSD')
        self.order_size = float(config.get('ORDER_SIZE', 0.001))
        self.dry_run = config.get('DRY_RUN', 'true').lower() == 'true'
        self.api_call_delay = float(config.get('API_CALL_DELAY', 1.0))

        # Adaptive settings
        self.reanalysis_interval = int(config.get('REANALYSIS_INTERVAL', 1800))  # 30 min default
        self.switch_cooldown = int(config.get('SWITCH_COOLDOWN', 3600))  # 1 hour default
        self.confirmations_required = int(config.get('CONFIRMATIONS_REQUIRED', 3))
        self.max_switches_per_day = int(config.get('MAX_SWITCHES_PER_DAY', 4))

        # Initialize analyzer and selector
        self.analyzer = MarketAnalyzer(config)
        self.selector = StrategySelector(config)

        # Initialize database
        self.db = TradingDatabase()
        self.entry_price = None
        self.entry_fee = None
        self.exit_fee = None
        self.current_position_id = None

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
            maker_fee=float(config.get('MAKER_FEE', 0.0016)),
            taker_fee=float(config.get('TAKER_FEE', 0.0026))
        )
        self.track_fees = config.get('TRACK_FEES', 'true').lower() == 'true'
        self.cumulative_fees = 0.0
        self.total_trades = 0
        self.net_pnl = 0.0

        logger.info(f"Adaptive Bot initialized for {self.trading_pair}")
        logger.info(f"Dry run mode: {self.dry_run}")
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

            return True
        except Exception as e:
            logger.error(f"Failed to access account: {e}")
            return False

    def get_market_data(self) -> Optional[dict]:
        """Get current market data."""
        try:
            ticker = self.client.get_ticker(self.trading_pair)
            order_book = self.client.get_order_book(self.trading_pair, count=10)

            return {
                'ticker': ticker,
                'order_book': order_book,
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
        ticker_data = market_data.get('ticker', {})

        # Find pair key
        pair_key = None
        for key in ticker_data.keys():
            if 'XXBT' in key or 'XBT' in key:
                pair_key = key
                break

        if not pair_key:
            return

        # Extract prices
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

            if self.dry_run:
                logger.info(f"[🔸 DRY RUN] Would place {order_type} {ordertype} order: "
                          f"{self.order_size} {self.trading_pair}" +
                          (f" @ ${price:,.2f}" if price else "") + " (dry_run=True)")
                return {'dry_run': True, 'type': order_type, 'ordertype': ordertype}

            logger.info(f"[⚠️  LIVE] Placing {order_type} {ordertype} order: "
                      f"{self.order_size} {self.trading_pair}" +
                      (f" @ ${price:,.2f}" if price else "") + " (dry_run=False)")
            result = self.client.add_order(
                pair=self.trading_pair,
                type=order_type,
                ordertype=ordertype,
                volume=self.order_size,
                price=price,
                validate=False
            )

            logger.info(f"Order placed: {result}")
            return result

        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            return None

    def record_entry(self, price: float, volume: float, fee: float = 0.0, dry_run: bool = True):
        """Record entry into a position."""
        self.entry_price = price
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

    def run_strategy(self):
        """Execute current strategy."""
        logger.info("Running strategy iteration...")

        # Get market data
        market_data = self.get_market_data()
        if not market_data:
            return

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
                            self.record_exit(current_price, self.order_size, dry_run=self.dry_run)

                    logger.info("Closing short position before going long")
                    self.place_order('buy')

                logger.info("Opening long position")
                result = self.place_order('buy')
                if result:
                    # Get current price and record entry
                    market_data_fresh = self.get_market_data()
                    if market_data_fresh:
                        ticker_data = market_data_fresh['ticker']
                        pair_key = self._get_pair_key(ticker_data)
                        if pair_key:
                            current_price = float(ticker_data[pair_key]['c'][0])
                            self.record_entry(current_price, self.order_size, dry_run=self.dry_run)

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
                            self.record_exit(current_price, self.order_size, dry_run=self.dry_run)

                    logger.info("Closing long position before going short")
                    self.place_order('sell')

                logger.info("Opening short position")
                result = self.place_order('sell')
                if result:
                    # Get current price and record entry
                    market_data_fresh = self.get_market_data()
                    if market_data_fresh:
                        ticker_data = market_data_fresh['ticker']
                        pair_key = self._get_pair_key(ticker_data)
                        if pair_key:
                            current_price = float(ticker_data[pair_key]['c'][0])
                            self.record_entry(current_price, self.order_size, dry_run=self.dry_run)

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
    api_key = os.getenv('KRAKEN_API_KEY')
    api_secret = os.getenv('KRAKEN_API_SECRET')

    if not api_key or not api_secret:
        logger.error("API credentials not found.")
        sys.exit(1)

    # Load configuration
    config = {
        'TRADING_PAIR': os.getenv('TRADING_PAIR', 'XBTUSD'),
        'ORDER_SIZE': os.getenv('ORDER_SIZE', '0.001'),
        'DRY_RUN': os.getenv('DRY_RUN', 'true'),
        'API_CALL_DELAY': os.getenv('API_CALL_DELAY', '1.0'),

        # Adaptive settings
        'REANALYSIS_INTERVAL': os.getenv('REANALYSIS_INTERVAL', '1800'),
        'SWITCH_COOLDOWN': os.getenv('SWITCH_COOLDOWN', '3600'),
        'CONFIRMATIONS_REQUIRED': os.getenv('CONFIRMATIONS_REQUIRED', '3'),
        'MAX_SWITCHES_PER_DAY': os.getenv('MAX_SWITCHES_PER_DAY', '4'),

        # Market analyzer thresholds
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
        'SUPPORT_LEVEL': os.getenv('SUPPORT_LEVEL', '96000'),
        'RESISTANCE_LEVEL': os.getenv('RESISTANCE_LEVEL', '102000'),
        'SUPPORT_ZONE': os.getenv('SUPPORT_ZONE', '3000'),
        'RESISTANCE_ZONE': os.getenv('RESISTANCE_ZONE', '3000'),
        'BREAKOUT_LOWER': os.getenv('BREAKOUT_LOWER', '93000'),
        'BREAKOUT_UPPER': os.getenv('BREAKOUT_UPPER', '106000'),
        'AUTO_DETECT_LEVELS': os.getenv('AUTO_DETECT_LEVELS', 'true'),
        'FAST_SMA_PERIOD': os.getenv('FAST_SMA_PERIOD', '10'),
        'SLOW_SMA_PERIOD': os.getenv('SLOW_SMA_PERIOD', '30'),

        # Fee accounting
        'MAKER_FEE': os.getenv('MAKER_FEE', '0.0016'),
        'TAKER_FEE': os.getenv('TAKER_FEE', '0.0026'),
        'TRACK_FEES': os.getenv('TRACK_FEES', 'true'),
        'MIN_PROFIT_PERCENT': os.getenv('MIN_PROFIT_PERCENT', '0.005'),
        'SKIP_UNPROFITABLE_TRADES': os.getenv('SKIP_UNPROFITABLE_TRADES', 'true'),
    }

    # Create and start bot
    bot = AdaptiveBot(api_key, api_secret, config)
    bot.start()


if __name__ == '__main__':
    main()
