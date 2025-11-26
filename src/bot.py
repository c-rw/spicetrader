"""
Main trading bot implementation.

DEPRECATED: This bot is deprecated in favor of adaptive_bot.py (single-coin)
or multi_coin_bot.py (multi-coin portfolio).

This file is kept for backward compatibility but is no longer maintained.
Please use adaptive_bot.py for single-coin adaptive trading.
"""
import os
import sys
import time
import logging
from typing import Optional
from dotenv import load_dotenv

from kraken.client import KrakenClient
from strategies import MeanReversionStrategy, SMACrossoverStrategy

# Configure logging
import pathlib
log_dir = pathlib.Path(__file__).parent.parent / 'logs'
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_dir / 'bot.log')
    ]
)
logger = logging.getLogger(__name__)


class TradingBot:
    """Main trading bot class."""

    def __init__(self, api_key: str, api_secret: str, config: dict):
        """
        Initialize trading bot.

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

        # Initialize strategy based on configuration
        strategy_name = config.get('STRATEGY', 'mean_reversion').lower()
        if strategy_name == 'mean_reversion':
            self.strategy = MeanReversionStrategy(config)
        elif strategy_name == 'sma_crossover':
            self.strategy = SMACrossoverStrategy(config)
        else:
            logger.error(f"Unknown strategy: {strategy_name}. Using mean_reversion.")
            self.strategy = MeanReversionStrategy(config)

        logger.info(f"Bot initialized for {self.trading_pair}")
        logger.info(f"Dry run mode: {self.dry_run}")
        logger.info(f"Strategy: {self.strategy.get_strategy_name()}")

    def check_connection(self) -> bool:
        """
        Check connection to Kraken API.

        Returns:
            True if connection successful
        """
        try:
            server_time = self.client.get_server_time()
            logger.info(f"Connected to Kraken. Server time: {server_time}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Kraken: {e}")
            return False

    def check_account(self) -> bool:
        """
        Check account access and balance.

        Returns:
            True if account accessible
        """
        try:
            balance = self.client.get_account_balance()
            logger.info(f"Account balance: {balance}")

            trade_balance = self.client.get_trade_balance()
            logger.info(f"Trade balance: {trade_balance}")

            return True
        except Exception as e:
            logger.error(f"Failed to access account: {e}")
            return False

    def get_market_data(self) -> Optional[dict]:
        """
        Get current market data for trading pair.

        Returns:
            Market data dictionary or None if failed
        """
        try:
            ticker = self.client.get_ticker(self.trading_pair)
            order_book = self.client.get_order_book(self.trading_pair, count=10)

            data = {
                'ticker': ticker,
                'order_book': order_book,
                'timestamp': time.time()
            }

            if self.trading_pair in ticker:
                pair_data = ticker[self.trading_pair]
                logger.info(f"Current price: Ask={pair_data['a'][0]}, Bid={pair_data['b'][0]}")

            return data

        except Exception as e:
            logger.error(f"Failed to get market data: {e}")
            return None

    def place_order(self, order_type: str, price: Optional[float] = None) -> Optional[dict]:
        """
        Place an order.

        Args:
            order_type: 'buy' or 'sell'
            price: Limit price (None for market order)

        Returns:
            Order result or None if failed
        """
        try:
            ordertype = 'limit' if price else 'market'

            if self.dry_run:
                logger.info(f"[DRY RUN] Would place {order_type} {ordertype} order: "
                          f"{self.order_size} {self.trading_pair}" +
                          (f" @ {price}" if price else ""))
                return {'dry_run': True, 'type': order_type, 'ordertype': ordertype}

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

    def cancel_all_orders(self) -> bool:
        """
        Cancel all open orders.

        Returns:
            True if successful
        """
        try:
            if self.dry_run:
                logger.info("[DRY RUN] Would cancel all orders")
                return True

            result = self.client.cancel_all_orders()
            logger.info(f"Orders cancelled: {result}")
            return True

        except Exception as e:
            logger.error(f"Failed to cancel orders: {e}")
            return False

    def run_strategy(self):
        """
        Main strategy execution - delegates to configured strategy.
        """
        logger.info("Running strategy iteration...")

        # Get market data
        market_data = self.get_market_data()
        if not market_data:
            return

        # Get signal from strategy
        signal = self.strategy.analyze(market_data)

        # Execute trade based on signal
        if signal:
            # Avoid duplicate signals
            if signal == self.strategy.last_signal:
                logger.info("Signal already acted upon, skipping...")
                return

            # Execute trade based on signal
            if signal == 'buy':
                # Close any short position first
                if self.strategy.position == 'short':
                    logger.info("Closing short position before going long")
                    self.place_order('buy')  # Buy to cover short

                # Open long position
                logger.info("Opening long position")
                result = self.place_order('buy')
                if result:
                    self.strategy.update_position('long')
                    self.strategy.update_signal('buy')

            elif signal == 'sell':
                # Close any long position first
                if self.strategy.position == 'long':
                    logger.info("Closing long position before going short")
                    self.place_order('sell')  # Sell to close long

                # Open short position (or just close long if shorting not desired)
                logger.info("Opening short position")
                result = self.place_order('sell')
                if result:
                    self.strategy.update_position('short')
                    self.strategy.update_signal('sell')

        logger.info("Strategy iteration complete")

    def start(self):
        """Start the trading bot."""
        logger.info("Starting trading bot...")

        # Check connection
        if not self.check_connection():
            logger.error("Failed to connect. Exiting.")
            return

        # Check account access
        if not self.check_account():
            logger.error("Failed to access account. Check API credentials.")
            return

        self.running = True
        logger.info("Bot is running. Press Ctrl+C to stop.")

        try:
            while self.running:
                # Run strategy
                self.run_strategy()

                # Wait before next iteration
                time.sleep(self.api_call_delay)

        except KeyboardInterrupt:
            logger.info("Received stop signal...")
            self.stop()

    def stop(self):
        """Stop the trading bot."""
        logger.info("Stopping trading bot...")
        self.running = False
        logger.info("Bot stopped")


def main():
    """Main entry point."""
    # Load environment variables
    load_dotenv()

    # Get API credentials
    api_key = os.getenv('KRAKEN_API_KEY')
    api_secret = os.getenv('KRAKEN_API_SECRET')

    if not api_key or not api_secret:
        logger.error("API credentials not found. Please set KRAKEN_API_KEY and KRAKEN_API_SECRET")
        logger.error("Copy .env.example to .env and add your credentials")
        sys.exit(1)

    # Load configuration
    config = {
        'TRADING_PAIR': os.getenv('TRADING_PAIR', 'XBTUSD'),
        'ORDER_SIZE': os.getenv('ORDER_SIZE', '0.001'),
        'DRY_RUN': os.getenv('DRY_RUN', 'true'),
        'API_CALL_DELAY': os.getenv('API_CALL_DELAY', '1.0'),
        'STRATEGY': os.getenv('STRATEGY', 'mean_reversion'),

        # SMA Crossover Strategy Parameters
        'FAST_SMA_PERIOD': os.getenv('FAST_SMA_PERIOD', '10'),
        'SLOW_SMA_PERIOD': os.getenv('SLOW_SMA_PERIOD', '30'),

        # Mean Reversion Strategy Parameters
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
    }

    # Create and start bot
    bot = TradingBot(api_key, api_secret, config)
    bot.start()


if __name__ == '__main__':
    main()
