"""CoinTrader - manages adaptive trading for a single cryptocurrency."""
import logging
import time
from typing import Optional, Dict, Any
from datetime import datetime
from collections import deque

from analysis import MarketAnalyzer, StrategySelector, MarketCondition
from fee_calculator import FeeCalculator
from database import TradingDatabase

logger = logging.getLogger(__name__)


class CoinTrader:
    """
    Manages adaptive trading for a single cryptocurrency.

    Each CoinTrader independently analyzes market conditions and
    executes trading strategies for one coin (e.g., BTC, SOL, ETH).
    """

    def __init__(self, symbol: str, config: Dict[str, Any], db: Optional[TradingDatabase] = None):
        """
        Initialize coin trader.

        Args:
            symbol: Trading pair symbol (e.g., 'XBTUSD', 'SOLUSD')
            config: Configuration dictionary
            db: Optional database instance
        """
        self.symbol = symbol
        self.config = config
        self.db = db

        # Extract coin-specific config
        self.order_size = float(config.get(f'{symbol}_ORDER_SIZE', config.get('ORDER_SIZE', 0.001)))
        self.max_position_pct = float(config.get(f'{symbol}_MAX_POSITION_PCT', 25.0))  # % of portfolio

        # Initialize analyzer and selector
        self.analyzer = MarketAnalyzer(config)
        self.selector = StrategySelector(config)

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

        # Performance tracking
        self.total_trades = 0
        self.winning_trades = 0
        self.total_pnl = 0.0

        # Fee tracking
        self.fee_calculator = FeeCalculator(
            maker_fee=float(config.get('MAKER_FEE', 0.0016)),
            taker_fee=float(config.get('TAKER_FEE', 0.0026))
        )
        self.track_fees = config.get('TRACK_FEES', 'true').lower() == 'true'
        self.cumulative_fees = 0.0
        self.total_volume = 0.0
        self.entry_price = None
        self.entry_fee = None
        self.exit_fee = None
        self.gross_pnl = 0.0
        self.net_pnl = 0.0
        self.current_position_id = None  # Track database position ID

        # Adaptive settings
        self.reanalysis_interval = int(config.get('REANALYSIS_INTERVAL', 1800))
        self.switch_cooldown = int(config.get('SWITCH_COOLDOWN', 3600))
        self.confirmations_required = int(config.get('CONFIRMATIONS_REQUIRED', 3))
        self.max_switches_per_day = int(config.get('MAX_SWITCHES_PER_DAY', 4))

        logger.info(f"CoinTrader initialized for {symbol}")
        logger.info(f"  Order Size: {self.order_size}")
        logger.info(f"  Max Position: {self.max_position_pct}% of portfolio")

    def should_reanalyze(self) -> bool:
        """Check if it's time to re-analyze market conditions."""
        if self.last_analysis_time is None:
            return True

        time_since_analysis = time.time() - self.last_analysis_time
        return time_since_analysis >= self.reanalysis_interval

    def can_switch_strategy(self) -> bool:
        """Check if strategy switching is allowed."""
        # Check daily limit
        today = datetime.now().date()
        if today != self.current_day:
            self.current_day = today
            self.switches_today = 0

        if self.switches_today >= self.max_switches_per_day:
            logger.warning(f"[{self.symbol}] Daily switch limit reached ({self.switches_today}/{self.max_switches_per_day})")
            return False

        # Check cooldown
        if self.last_switch_time is None:
            return True

        time_since_switch = time.time() - self.last_switch_time
        if time_since_switch < self.switch_cooldown:
            return False

        return True

    def analyze_and_update_strategy(self):
        """Analyze market and update strategy if needed."""
        # Need enough data - check this first, before reanalysis interval
        min_required = self.analyzer.get_required_data_points()
        if len(self.price_history) < min_required:
            logger.info(f"[{self.symbol}] Collecting data... ({len(self.price_history)}/{min_required})")
            # Don't update last_analysis_time - we want to check data collection every iteration
            return

        # Only enforce reanalysis interval after we have enough data
        if not self.should_reanalyze():
            return

        # Analyze current market (with caching by symbol)
        # Convert deques to lists for slicing support in indicators
        market_condition = self.analyzer.analyze(
            list(self.price_history),
            list(self.high_history),
            list(self.low_history),
            symbol=self.symbol
        )

        self.current_market_condition = market_condition
        self.last_analysis_time = time.time()

        logger.info(f"[{self.symbol}] Market: {market_condition.state.value} | Confidence: {market_condition.confidence*100:.0f}%")

        # Get recommended strategy
        recommended_strategy_name = market_condition.get_recommended_strategy()

        # If no current strategy, set it
        if self.current_strategy is None:
            logger.info(f"[{self.symbol}] Initial strategy: {recommended_strategy_name}")
            self.current_strategy = self.selector.select_strategy(market_condition, symbol=self.symbol)
            return

        # Check if recommended strategy is different
        current_strategy_name = self._get_strategy_name(self.current_strategy)

        if recommended_strategy_name == current_strategy_name:
            if self.pending_confirmations > 0:
                logger.debug(f"[{self.symbol}] Strategy confirmation reset")
            self.pending_state = None
            self.pending_confirmations = 0
            return

        # Different strategy recommended
        logger.info(f"[{self.symbol}] New strategy recommended: {recommended_strategy_name} (current: {current_strategy_name})")

        # Check if it's the same as pending
        if self.pending_state == market_condition.state:
            self.pending_confirmations += 1
            logger.info(f"[{self.symbol}] Confirmation {self.pending_confirmations}/{self.confirmations_required}")
        else:
            self.pending_state = market_condition.state
            self.pending_confirmations = 1

        # Check if we have enough confirmations
        if self.pending_confirmations >= self.confirmations_required:
            if self.can_switch_strategy():
                self._switch_strategy(market_condition, recommended_strategy_name)

    def _switch_strategy(self, market_condition: MarketCondition, new_strategy_name: str):
        """Switch to a new strategy."""
        old_strategy_name = self._get_strategy_name(self.current_strategy)

        logger.info(f"[{self.symbol}] 🔄 SWITCHING: {old_strategy_name} → {new_strategy_name}")
        logger.info(f"[{self.symbol}] Reason: {market_condition.description}")

        # Close any open positions
        if self.current_strategy and self.current_strategy.position:
            logger.info(f"[{self.symbol}] Closing {self.current_strategy.position} position")
            self.current_strategy.update_position(None)

        # Select new strategy
        self.current_strategy = self.selector.select_strategy(market_condition, symbol=self.symbol)

        # Update tracking
        self.last_switch_time = time.time()
        self.switches_today += 1
        self.pending_state = None
        self.pending_confirmations = 0

        logger.info(f"[{self.symbol}] ✅ Switched ({self.switches_today}/{self.max_switches_per_day} today)")

    def update_price_history(self, close: float, high: float, low: float):
        """Update price history. Deque automatically maintains max size."""
        self.price_history.append(close)
        self.high_history.append(high)
        self.low_history.append(low)

    def analyze(self, market_data: Dict[str, Any]) -> Optional[str]:
        """
        Analyze market and return trading signal.

        Args:
            market_data: Market data dictionary

        Returns:
            'buy', 'sell', or None
        """
        # Update price history
        ticker_data = market_data.get('ticker', {})
        if not ticker_data:
            return None

        # Find pair key
        pair_key = self._find_pair_key(ticker_data)
        if not pair_key:
            return None

        ticker = ticker_data[pair_key]
        close = float(ticker['c'][0])
        high = float(ticker['h'][0])
        low = float(ticker['l'][0])

        self.update_price_history(close, high, low)

        # Analyze and potentially switch strategy
        self.analyze_and_update_strategy()

        # If no strategy yet, wait
        if self.current_strategy is None:
            return None

        # Update strategy with current market state
        if self.current_market_condition:
            self.current_strategy.update_market_state(self.current_market_condition.state.value)

        # Run current strategy
        signal = self.current_strategy.analyze(market_data)

        return signal

    def _get_strategy_name(self, strategy) -> str:
        """Get strategy name from strategy instance."""
        if strategy is None:
            return "none"
        class_name = strategy.__class__.__name__
        return class_name.replace('Strategy', '').lower()

    def _find_pair_key(self, ticker_data: dict) -> Optional[str]:
        """Find the actual trading pair key in ticker response."""
        # Extract base from symbol (e.g., 'XBTUSD' -> try XXBTZUSD)
        if self.symbol in ticker_data:
            return self.symbol

        # Try common variations
        variations = [
            self.symbol,
            self.symbol.replace('XBT', 'XXBT').replace('USD', 'ZUSD'),
            self.symbol.replace('SOL', 'SOL').replace('USD', 'USD'),
            self.symbol.replace('ETH', 'XETH').replace('USD', 'ZUSD'),
            self.symbol.replace('XMR', 'XXMR').replace('USD', 'ZUSD'),
        ]

        for variation in variations:
            if variation in ticker_data:
                return variation

        # Return first key if none match
        if ticker_data:
            return list(ticker_data.keys())[0]

        return None

    def record_entry(self, price: float, volume: float, fee: float = 0.0, dry_run: bool = True):
        """
        Record entry into a position.

        Args:
            price: Entry price
            volume: Position size
            fee: Fee paid (if known), otherwise estimated
            dry_run: Whether this is a dry run trade
        """
        self.entry_price = price
        self.entry_fee = fee if fee > 0 else self.fee_calculator.calculate_fee(price * volume)

        if self.track_fees:
            self.cumulative_fees += self.entry_fee
            self.total_volume += price * volume

        dry_run_label = "dry_run=True (TEST)" if dry_run else "dry_run=False (LIVE)"
        logger.info(f"[{self.symbol}] Entry recorded: ${price:,.2f}, fee: ${self.entry_fee:.2f} ({dry_run_label})")

        # Record in database
        if self.db and self.current_strategy:
            position_type = self.current_strategy.position if self.current_strategy.position else 'long'
            market_state = self.current_market_condition.state.value if self.current_market_condition else None
            strategy_name = self._get_strategy_name(self.current_strategy)

            # Open position in database
            self.current_position_id = self.db.open_position(
                symbol=self.symbol,
                strategy=strategy_name,
                position_type=position_type,
                entry_price=price,
                entry_volume=volume,
                entry_fee=self.entry_fee,
                market_state=market_state,
                dry_run=dry_run
            )

            # Record trade
            self.db.record_trade(
                symbol=self.symbol,
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
        """
        Record exit from a position and calculate P&L.

        Args:
            price: Exit price
            volume: Position size
            fee: Fee paid (if known), otherwise estimated
            dry_run: Whether this is a dry run trade
        """
        if self.entry_price is None:
            logger.warning(f"[{self.symbol}] Exit recorded but no entry price!")
            return

        self.exit_fee = fee if fee > 0 else self.fee_calculator.calculate_fee(price * volume)

        # Calculate P&L
        position_type = 'long' if self.current_strategy and self.current_strategy.position == 'long' else 'short'
        gross_pnl, total_fees, net_pnl = self.fee_calculator.calculate_net_pnl(
            entry_price=self.entry_price,
            exit_price=price,
            volume=volume,
            position_type=position_type,
            entry_fee=self.entry_fee,
            exit_fee=self.exit_fee
        )

        # Update statistics
        self.gross_pnl += gross_pnl
        self.net_pnl += net_pnl
        self.total_pnl = self.net_pnl  # Legacy field

        if net_pnl > 0:
            self.winning_trades += 1

        if self.track_fees:
            self.cumulative_fees += self.exit_fee
            self.total_volume += price * volume

        dry_run_label = "dry_run=True (TEST)" if dry_run else "dry_run=False (LIVE)"
        logger.info(
            f"[{self.symbol}] Exit recorded: ${price:,.2f}, "
            f"Gross P&L: ${gross_pnl:.2f}, Fees: ${total_fees:.2f}, Net P&L: ${net_pnl:.2f} ({dry_run_label})"
        )

        # Record in database
        if self.db and self.current_position_id:
            # Close position in database
            self.db.close_position(
                position_id=self.current_position_id,
                exit_price=price,
                exit_volume=volume,
                exit_fee=self.exit_fee
            )

            # Record exit trade
            strategy_name = self._get_strategy_name(self.current_strategy) if self.current_strategy else 'unknown'
            market_state = self.current_market_condition.state.value if self.current_market_condition else None

            self.db.record_trade(
                symbol=self.symbol,
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

        # Reset for next trade
        self.entry_price = None
        self.entry_fee = None
        self.exit_fee = None

    def get_fee_summary(self) -> dict:
        """Get fee summary statistics."""
        if not self.track_fees:
            return {}

        return self.fee_calculator.get_fee_summary(
            cumulative_fees=self.cumulative_fees,
            total_volume=self.total_volume
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get trading statistics."""
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0

        stats = {
            'symbol': self.symbol,
            'strategy': self._get_strategy_name(self.current_strategy),
            'market_state': self.current_market_condition.state.value if self.current_market_condition else 'unknown',
            'position': self.current_strategy.position if self.current_strategy else None,
            'total_trades': self.total_trades,
            'win_rate': win_rate,
            'gross_pnl': self.gross_pnl,
            'net_pnl': self.net_pnl,
            'total_pnl': self.total_pnl,
            'switches_today': self.switches_today,
        }

        # Add fee statistics if tracking
        if self.track_fees:
            stats.update({
                'cumulative_fees': self.cumulative_fees,
                'total_volume': self.total_volume,
                'fee_percent': (self.cumulative_fees / self.total_volume * 100) if self.total_volume > 0 else 0
            })

        return stats
