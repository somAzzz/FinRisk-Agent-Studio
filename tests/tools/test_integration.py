"""Integration tests for tiered routing flow."""
import pytest
from unittest.mock import patch, MagicMock


def test_full_flow_ddgs_fallback_to_searxng():
    """ddgs failure should trigger SearXNG transparently."""
    from src.tools.router import ToolRouter

    router = ToolRouter()

    # First call fails, second (searxng) succeeds
    with patch("src.tools.router.web_search") as mock_ddgs, \
         patch("src.tools.router.searxng_search") as mock_searxng:
        mock_ddgs.side_effect = Exception("Rate limit")  # raises when called
        mock_searxng.return_value = '{"source": "searxng", "results": []}'

        result = router.execute_ddgs("test query")
        mock_searxng.assert_called_once()