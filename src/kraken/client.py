"""Kraken API client wrapper."""
import time
import hmac
import hashlib
import base64
import urllib.parse
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Any, Optional, Tuple
import requests
import logging

logger = logging.getLogger(__name__)


class KrakenClient:
    """Wrapper for Kraken REST API with authentication and error handling."""

    BASE_URL = "https://api.kraken.com"
    API_VERSION = "0"

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        """
        Initialize Kraken API client.

        Args:
            api_key: Kraken API key
            api_secret: Kraken API secret
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'SpiceTrader/1.0'
        })

        # Cache AssetPairs metadata for order validation/rounding.
        self._asset_pairs_cache: Dict[str, Dict[str, Any]] = {}

    def _get_kraken_signature(self, urlpath: str, data: Dict[str, Any], nonce: str) -> str:
        """
        Generate authentication signature for private endpoints.

        Args:
            urlpath: API endpoint path
            data: Request data including nonce
            nonce: Unique nonce value

        Returns:
            Base64-encoded signature
        """
        postdata = urllib.parse.urlencode(data)
        encoded = (str(data['nonce']) + postdata).encode()
        message = urlpath.encode() + hashlib.sha256(encoded).digest()

        mac = hmac.new(base64.b64decode(self.api_secret), message, hashlib.sha512)
        sigdigest = base64.b64encode(mac.digest())
        return sigdigest.decode()

    def _make_request(self, endpoint: str, data: Optional[Dict[str, Any]] = None,
                     private: bool = False, max_retries: int = 3) -> Dict[str, Any]:
        """
        Make HTTP request to Kraken API with retry logic.

        Args:
            endpoint: API endpoint (e.g., 'Ticker', 'Balance')
            data: Request parameters
            private: Whether this is a private endpoint requiring authentication
            max_retries: Maximum number of retry attempts for transient errors

        Returns:
            API response data

        Raises:
            Exception: If API returns errors after all retries
        """
        if data is None:
            data = {}

        # Construct URL
        if private:
            url_path = f"/{self.API_VERSION}/private/{endpoint}"
        else:
            url_path = f"/{self.API_VERSION}/public/{endpoint}"

        url = self.BASE_URL + url_path

        # Retry loop with exponential backoff
        last_exception = None
        for attempt in range(max_retries):
            try:
                # Add authentication for private endpoints
                headers = {}
                if private:
                    if not self.api_key or not self.api_secret:
                        raise ValueError("API key and secret required for private endpoints")

                    nonce = str(int(time.time() * 1000))
                    data['nonce'] = nonce

                    headers['API-Key'] = self.api_key
                    headers['API-Sign'] = self._get_kraken_signature(url_path, data, nonce)

                # Make request with increased timeout
                timeout = 45  # Increased from 30 to handle slow responses
                if private:
                    response = self.session.post(url, data=data, headers=headers, timeout=timeout)
                else:
                    response = self.session.get(url, params=data, timeout=timeout)

                response.raise_for_status()
                result = response.json()

                # Check for API errors
                if result.get('error'):
                    error_msg = ', '.join(result['error'])
                    logger.error(f"API Error: {error_msg}")
                    raise Exception(f"Kraken API Error: {error_msg}")

                return result.get('result', {})

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                last_exception = e
                if attempt < max_retries - 1:
                    # Exponential backoff: 2s, 4s, 8s
                    wait_time = 2 ** (attempt + 1)
                    logger.warning(f"Request timeout/connection error (attempt {attempt + 1}/{max_retries}). Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Request failed after {max_retries} attempts: {e}")
                    raise
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {e}")
                raise

        # Should never reach here, but just in case
        if last_exception:
            raise last_exception

    # ==================== PUBLIC ENDPOINTS ====================

    def get_server_time(self) -> Dict[str, Any]:
        """Get Kraken server time."""
        return self._make_request('Time')

    def get_asset_info(self, assets: Optional[str] = None) -> Dict[str, Any]:
        """
        Get information about assets.

        Args:
            assets: Comma-separated list of assets to query (optional)
        """
        data = {}
        if assets:
            data['asset'] = assets
        return self._make_request('Assets', data)

    def get_tradable_pairs(self, pair: Optional[str] = None) -> Dict[str, Any]:
        """
        Get tradable asset pairs.

        Args:
            pair: Comma-separated list of pairs to query (optional)
        """
        data = {}
        if pair:
            data['pair'] = pair
        return self._make_request('AssetPairs', data)

    def _select_asset_pair_key(self, requested_pair: str, asset_pairs: Dict[str, Any]) -> Optional[str]:
        """Pick the best-matching key from an AssetPairs response."""
        if not asset_pairs:
            return None

        if requested_pair in asset_pairs:
            return requested_pair

        for key, info in asset_pairs.items():
            try:
                if isinstance(info, dict) and info.get('altname') == requested_pair:
                    return key
            except Exception:
                continue

        # Fallback: some callers provide XBTUSD while Kraken may return XXBTZUSD
        variations = [
            requested_pair.replace('XBT', 'XXBT').replace('USD', 'ZUSD'),
            requested_pair.replace('ETH', 'XETH').replace('USD', 'ZUSD'),
            requested_pair.replace('XRP', 'XXRP').replace('USD', 'ZUSD'),
            requested_pair.replace('XMR', 'XXMR').replace('USD', 'ZUSD'),
        ]
        for v in variations:
            if v in asset_pairs:
                return v

        return next(iter(asset_pairs.keys()), None)

    def get_asset_pair_rules(self, pair: str, refresh: bool = False) -> Dict[str, Any]:
        """Return AssetPairs metadata for a requested pair (cached)."""
        if not refresh and pair in self._asset_pairs_cache:
            return self._asset_pairs_cache[pair]

        asset_pairs = self.get_tradable_pairs(pair)
        key = self._select_asset_pair_key(pair, asset_pairs)
        if not key or key not in asset_pairs:
            raise ValueError(f"AssetPairs did not return rules for pair={pair}")

        rules = asset_pairs[key]
        if not isinstance(rules, dict):
            raise ValueError(f"Unexpected AssetPairs rules shape for pair={pair}")

        self._asset_pairs_cache[pair] = rules
        return rules

    @staticmethod
    def _round_down_decimal(value: Decimal, decimals: int) -> Decimal:
        if decimals < 0:
            return value
        quant = Decimal('1').scaleb(-decimals)
        return value.quantize(quant, rounding=ROUND_DOWN)

    @staticmethod
    def _round_down_to_tick(value: Decimal, tick_size: Decimal) -> Decimal:
        if tick_size <= 0:
            return value
        # Floor to nearest tick.
        return (value // tick_size) * tick_size

    @classmethod
    def normalize_order_with_rules(
        cls,
        rules: Dict[str, Any],
        *,
        ordertype: str,
        volume: float,
        price: Optional[float] = None,
        current_price: Optional[float] = None,
    ) -> Tuple[float, Optional[float]]:
        """Normalize volume/price according to Kraken AssetPairs metadata.

        - Rounds volume down to `lot_decimals`
        - Rounds limit price down to `tick_size` (or `pair_decimals`)
        - Enforces `ordermin`
        - Enforces `costmin` when a price estimate is available
        """
        lot_decimals = int(rules.get('lot_decimals', 8))
        pair_decimals = int(rules.get('pair_decimals', 5))

        volume_dec = Decimal(str(volume))
        volume_dec = cls._round_down_decimal(volume_dec, lot_decimals)
        if volume_dec <= 0:
            raise ValueError("Order volume rounds to 0")

        ordermin = rules.get('ordermin')
        if ordermin is not None:
            if volume_dec < Decimal(str(ordermin)):
                raise ValueError(f"Order volume {volume_dec} below ordermin {ordermin}")

        normalized_price: Optional[Decimal] = None
        if price is not None and ordertype != 'market':
            price_dec = Decimal(str(price))

            tick_size_raw = rules.get('tick_size')
            if tick_size_raw is not None:
                tick_size = Decimal(str(tick_size_raw))
                if tick_size > 0:
                    price_dec = cls._round_down_to_tick(price_dec, tick_size)

            price_dec = cls._round_down_decimal(price_dec, pair_decimals)
            if price_dec <= 0:
                raise ValueError("Order price rounds to 0")
            normalized_price = price_dec

        # Enforce minimum cost when we can estimate it.
        costmin = rules.get('costmin')
        price_for_cost = normalized_price
        if price_for_cost is None and current_price is not None:
            price_for_cost = Decimal(str(current_price))
        if costmin is not None and price_for_cost is not None:
            cost = volume_dec * price_for_cost
            if cost < Decimal(str(costmin)):
                raise ValueError(f"Order cost {cost} below costmin {costmin}")

        return (float(volume_dec), float(normalized_price) if normalized_price is not None else None)

    def normalize_order(
        self,
        *,
        pair: str,
        ordertype: str,
        volume: float,
        price: Optional[float] = None,
        current_price: Optional[float] = None,
    ) -> Tuple[float, Optional[float]]:
        rules = self.get_asset_pair_rules(pair)
        return self.normalize_order_with_rules(
            rules,
            ordertype=ordertype,
            volume=volume,
            price=price,
            current_price=current_price,
        )

    def get_ticker(self, pair: str) -> Dict[str, Any]:
        """
        Get ticker information for pair(s).

        Args:
            pair: Asset pair(s) to get data for (e.g., 'XBTUSD')
        """
        return self._make_request('Ticker', {'pair': pair})

    def get_ohlc(self, pair: str, interval: int = 1, since: Optional[int] = None) -> Dict[str, Any]:
        """
        Get OHLC data.

        Args:
            pair: Asset pair (e.g., 'XBTUSD')
            interval: Time interval in minutes (1, 5, 15, 30, 60, 240, 1440, 10080, 21600)
            since: Return data since given timestamp
        """
        data = {'pair': pair, 'interval': interval}
        if since:
            data['since'] = since
        return self._make_request('OHLC', data)

    def get_order_book(self, pair: str, count: Optional[int] = None) -> Dict[str, Any]:
        """
        Get order book depth.

        Args:
            pair: Asset pair (e.g., 'XBTUSD')
            count: Maximum number of asks/bids (optional)
        """
        data = {'pair': pair}
        if count:
            data['count'] = count
        return self._make_request('Depth', data)

    def get_recent_trades(self, pair: str, since: Optional[int] = None) -> Dict[str, Any]:
        """
        Get recent trades.

        Args:
            pair: Asset pair (e.g., 'XBTUSD')
            since: Return trades since given timestamp
        """
        data = {'pair': pair}
        if since:
            data['since'] = since
        return self._make_request('Trades', data)

    def get_spread(self, pair: str, since: Optional[int] = None) -> Dict[str, Any]:
        """
        Get spread data.

        Args:
            pair: Asset pair (e.g., 'XBTUSD')
            since: Return data since given timestamp
        """
        data = {'pair': pair}
        if since:
            data['since'] = since
        return self._make_request('Spread', data)

    # ==================== PRIVATE ENDPOINTS ====================

    def get_account_balance(self) -> Dict[str, Any]:
        """Get account balance."""
        return self._make_request('Balance', private=True)

    def get_trade_balance(self, asset: str = 'ZUSD') -> Dict[str, Any]:
        """
        Get trade balance.

        Args:
            asset: Base asset for balance (default: ZUSD)
        """
        return self._make_request('TradeBalance', {'asset': asset}, private=True)

    def get_open_orders(self, trades: bool = False) -> Dict[str, Any]:
        """
        Get open orders.

        Args:
            trades: Whether to include trades (default: False)
        """
        return self._make_request('OpenOrders', {'trades': trades}, private=True)

    def get_closed_orders(self, trades: bool = False, start: Optional[int] = None,
                         end: Optional[int] = None) -> Dict[str, Any]:
        """
        Get closed orders.

        Args:
            trades: Whether to include trades
            start: Starting timestamp
            end: Ending timestamp
        """
        data = {'trades': trades}
        if start:
            data['start'] = start
        if end:
            data['end'] = end
        return self._make_request('ClosedOrders', data, private=True)

    def query_orders(self, txid: str, trades: bool = False) -> Dict[str, Any]:
        """
        Query specific orders.

        Args:
            txid: Transaction ID(s) (comma-separated)
            trades: Whether to include trades
        """
        return self._make_request('QueryOrders', {'txid': txid, 'trades': trades}, private=True)

    def get_trades_history(self, start: Optional[int] = None, end: Optional[int] = None,
                          ofs: Optional[int] = None) -> Dict[str, Any]:
        """
        Get trades history.

        Args:
            start: Starting timestamp
            end: Ending timestamp
            ofs: Result offset
        """
        data = {}
        if start:
            data['start'] = start
        if end:
            data['end'] = end
        if ofs:
            data['ofs'] = ofs
        return self._make_request('TradesHistory', data, private=True)

    def query_ledgers(self, id: Optional[str] = None, start: Optional[int] = None,
                     end: Optional[int] = None, ofs: Optional[int] = None,
                     type: Optional[str] = None) -> Dict[str, Any]:
        """
        Query ledger entries (includes actual fees paid).

        Args:
            id: Comma-separated list of ledger IDs to query (optional)
            start: Starting timestamp (optional)
            end: Ending timestamp (optional)
            ofs: Result offset (optional)
            type: Type of ledger to retrieve (optional):
                  'all', 'deposit', 'withdrawal', 'trade', 'margin', etc.

        Returns:
            Dictionary with ledger entries including actual fees

        Example response:
            {
                'ledger': {
                    'LEDGER-ID': {
                        'refid': 'TRADE-ID',
                        'time': 1234567890.1234,
                        'type': 'trade',
                        'subtype': '',
                        'aclass': 'currency',
                        'asset': 'ZUSD',
                        'amount': '-100.00',
                        'fee': '0.26',
                        'balance': '900.00'
                    }
                },
                'count': 1
            }
        """
        data = {}
        if id:
            data['id'] = id
        if start:
            data['start'] = start
        if end:
            data['end'] = end
        if ofs:
            data['ofs'] = ofs
        if type:
            data['type'] = type
        return self._make_request('QueryLedgers', data, private=True)

    def get_trade_volume(self, pair: Optional[str] = None, fee_info: bool = True) -> Dict[str, Any]:
        """
        Get trade volume and fee tier information.

        Args:
            pair: Comma-separated list of asset pairs (optional)
            fee_info: Whether to include fee info (default: True)

        Returns:
            Dictionary with volume and fee tier information

        Example response:
            {
                'currency': 'ZUSD',
                'volume': '12345.67',
                'fees': {
                    'XBTUSD': {'fee': '0.26', 'minfee': '0.10', 'maxfee': '0.26',
                               'nextfee': '0.24', 'nextvolume': '50000.00', 'tiervolume': '0.00'}
                },
                'fees_maker': {
                    'XBTUSD': {'fee': '0.16', 'minfee': '0.00', 'maxfee': '0.16',
                               'nextfee': '0.14', 'nextvolume': '50000.00', 'tiervolume': '0.00'}
                }
            }
        """
        data = {}
        if pair:
            data['pair'] = pair
        if fee_info:
            data['fee-info'] = 'true'
        return self._make_request('TradeVolume', data, private=True)

    def add_order(self, pair: str, type: str, ordertype: str, volume: float,
                  price: Optional[float] = None, price2: Optional[float] = None,
                  leverage: Optional[str] = None, oflags: Optional[str] = None,
                  validate: bool = False, **kwargs) -> Dict[str, Any]:
        """
        Add new order.

        Args:
            pair: Asset pair (e.g., 'XBTUSD')
            type: Order type ('buy' or 'sell')
            ordertype: Order type ('market', 'limit', 'stop-loss', etc.)
            volume: Order volume
            price: Price (required for limit orders)
            price2: Secondary price (for stop-loss-limit)
            leverage: Leverage (e.g., '2:1')
            oflags: Order flags (comma-separated: 'viqc', 'fcib', 'fciq', 'nompp', 'post')
            validate: Validate only (don't submit order)
            **kwargs: Additional parameters
        """
        data = {
            'pair': pair,
            'type': type,
            'ordertype': ordertype,
            'volume': str(volume),
        }

        if price:
            data['price'] = str(price)
        if price2:
            data['price2'] = str(price2)
        if leverage:
            data['leverage'] = leverage
        if oflags:
            data['oflags'] = oflags
        if validate:
            data['validate'] = 'true'

        data.update(kwargs)

        return self._make_request('AddOrder', data, private=True)

    def cancel_order(self, txid: str) -> Dict[str, Any]:
        """
        Cancel open order.

        Args:
            txid: Transaction ID
        """
        return self._make_request('CancelOrder', {'txid': txid}, private=True)

    def cancel_all_orders(self) -> Dict[str, Any]:
        """Cancel all open orders."""
        return self._make_request('CancelAll', private=True)

    def get_order_fee(self, txid: str) -> dict:
        """
        Get fee information for a specific order.

        Args:
            txid: Transaction ID from order placement

        Returns:
            dict: Fee information including:
                - fee: Total fee amount
                - fee_currency: Fee currency
                - trades: List of trades with individual fees
        """
        try:
            # Query the order with trade details
            result = self.query_orders(txid, trades=True)

            if not result or txid not in result:
                return {'fee': 0.0, 'fee_currency': 'USD', 'trades': []}

            order = result[txid]
            trades = order.get('trades', [])

            total_fee = 0.0
            fee_currency = 'USD'
            trade_details = []

            # Sum up fees from all trades
            for trade_id in trades:
                # Get trade details
                trade_info = self.get_trades_history(txid=trade_id)
                if trade_info and 'trades' in trade_info:
                    for tid, trade in trade_info['trades'].items():
                        fee = float(trade.get('fee', 0.0))
                        total_fee += fee

                        trade_details.append({
                            'trade_id': tid,
                            'fee': fee,
                            'cost': float(trade.get('cost', 0.0)),
                            'vol': float(trade.get('vol', 0.0)),
                            'price': float(trade.get('price', 0.0))
                        })

            return {
                'fee': total_fee,
                'fee_currency': fee_currency,
                'trades': trade_details,
                'total_fee': total_fee
            }

        except Exception as e:
            logger.error(f"Failed to get order fee for {txid}: {e}")
            return {'fee': 0.0, 'fee_currency': 'USD', 'trades': []}

    def extract_fee_from_response(self, order_response: dict) -> float:
        """
        Extract fee from order add response (estimate).

        Args:
            order_response: Response from add_order()

        Returns:
            float: Estimated fee (0.0 if not available)

        Note:
            Order add response doesn't include actual fees.
            Use get_order_fee() after order fills for actual fees.
        """
        # Order response only has txid, not fee info
        # Return 0 and let caller use get_order_fee() later
        return 0.0

    def get_trade_actual_fee(self, txid: str, max_wait_seconds: int = 10) -> float:
        """
        Get actual fee for a trade using ledger lookup.

        This method queries the ledger to find the actual fee charged,
        waiting briefly for the trade to settle if needed.

        Args:
            txid: Transaction ID from order placement
            max_wait_seconds: Maximum time to wait for trade to appear in ledger

        Returns:
            float: Actual fee charged, or 0.0 if not found
        """
        import time

        start_time = time.time()
        wait_interval = 0.5  # Check every 0.5 seconds

        while (time.time() - start_time) < max_wait_seconds:
            try:
                # Query recent ledger entries for trades
                ledger_result = self.query_ledgers(type='trade')

                if 'ledger' in ledger_result:
                    # Look through ledger entries for matching trade
                    for ledger_id, entry in ledger_result['ledger'].items():
                        # Check if this ledger entry references our trade
                        if entry.get('refid') == txid:
                            fee = float(entry.get('fee', 0.0))
                            logger.info(f"Found actual fee for {txid}: ${fee:.2f}")
                            return fee

                # If not found, wait and retry
                time.sleep(wait_interval)

            except Exception as e:
                logger.warning(f"Error querying ledger for {txid}: {e}")
                break

        logger.warning(f"Could not find actual fee for {txid} after {max_wait_seconds}s")
        return 0.0

    def get_websocket_token(self) -> Dict[str, Any]:
        """Get authentication token for WebSocket API."""
        return self._make_request('GetWebSocketsToken', private=True)
