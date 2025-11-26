"""Tests for Kraken API client."""
import pytest
from unittest.mock import Mock, patch
from src.kraken.client import KrakenClient


class TestKrakenClient:
    """Test suite for KrakenClient."""

    def test_client_initialization(self):
        """Test client initializes correctly."""
        client = KrakenClient()
        assert client.BASE_URL == "https://api.kraken.com"
        assert client.API_VERSION == "0"
        assert client.api_key is None
        assert client.api_secret is None

    def test_client_with_credentials(self):
        """Test client initializes with credentials."""
        client = KrakenClient(api_key="test_key", api_secret="test_secret")
        assert client.api_key == "test_key"
        assert client.api_secret == "test_secret"

    @patch('src.kraken.client.requests.Session.get')
    def test_get_server_time(self, mock_get):
        """Test get_server_time endpoint."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'error': [],
            'result': {'unixtime': 1234567890, 'rfc1123': 'Mon, 01 Jan 2024 00:00:00 +0000'}
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = KrakenClient()
        result = client.get_server_time()

        assert 'unixtime' in result
        assert result['unixtime'] == 1234567890
        mock_get.assert_called_once()

    @patch('src.kraken.client.requests.Session.get')
    def test_get_ticker(self, mock_get):
        """Test get_ticker endpoint."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'error': [],
            'result': {
                'XXBTZUSD': {
                    'a': ['50000.00000', '1', '1.000'],
                    'b': ['49999.00000', '2', '2.000'],
                    'c': ['50000.00000', '0.00100000']
                }
            }
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        client = KrakenClient()
        result = client.get_ticker('XBTUSD')

        assert 'XXBTZUSD' in result
        mock_get.assert_called_once()

    def test_private_endpoint_without_credentials(self):
        """Test private endpoint raises error without credentials."""
        client = KrakenClient()

        with pytest.raises(ValueError, match="API key and secret required"):
            client.get_account_balance()

    @patch('src.kraken.client.requests.Session.post')
    def test_api_error_handling(self, mock_post):
        """Test API error handling."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'error': ['EAPI:Invalid key']
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        client = KrakenClient(api_key="test", api_secret="dGVzdA==")  # base64 encoded "test"

        with pytest.raises(Exception, match="Kraken API Error"):
            client.get_account_balance()
