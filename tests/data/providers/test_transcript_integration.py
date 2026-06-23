"""Optional transcript-provider integration tests.

These tests are skipped by default. Enable them with::

    RUN_TRANSCRIPT_INTEGRATION=1 uv run pytest \\
        tests/data/providers/test_transcript_integration.py -m integration

They hit the real FMP or Alpha Vantage API. Use sparingly.
"""

from __future__ import annotations

import os

import pytest

from src.data.providers.alpha_vantage import AlphaVantageProvider
from src.data.providers.fmp import FMPProvider
from src.data.transcripts import (
    TranscriptNotFoundError,
    TranscriptProviderConfigError,
)


pytestmark = pytest.mark.integration


def _integration_enabled() -> bool:
    return os.environ.get("RUN_TRANSCRIPT_INTEGRATION") == "1"


skip_unless = pytest.mark.skipif(
    not _integration_enabled(),
    reason="set RUN_TRANSCRIPT_INTEGRATION=1 to enable",
)


@skip_unless
def test_fmp_provider_missing_key_raises_config_error() -> None:
    """The FMP provider raises TranscriptProviderConfigError without a key.

    We deliberately do not set FMP_API_KEY in this test, so the constructor
    should refuse to instantiate.
    """
    import os

    saved = os.environ.pop("FMP_API_KEY", None)
    try:
        with pytest.raises(TranscriptProviderConfigError):
            FMPProvider()
    finally:
        if saved is not None:
            os.environ["FMP_API_KEY"] = saved


@skip_unless
def test_alpha_vantage_provider_missing_key_raises_config_error() -> None:
    import os

    saved = os.environ.pop("ALPHA_VANTAGE_API_KEY", None)
    try:
        with pytest.raises(TranscriptProviderConfigError):
            AlphaVantageProvider()
    finally:
        if saved is not None:
            os.environ["ALPHA_VANTAGE_API_KEY"] = saved


@skip_unless
@pytest.mark.skipif(
    not os.environ.get("FMP_API_KEY"),
    reason="FMP_API_KEY not set",
)
def test_fmp_provider_returns_transcript_or_not_found() -> None:
    """A configured FMP provider either returns a Transcript or raises NotFound.

    The exact behavior depends on the company's filing history; the test
    only requires that the provider does not crash and produces a typed
    outcome.
    """
    provider = FMPProvider()
    try:
        transcript = provider.get_transcript("AAPL", 2024, 4)
    except TranscriptNotFoundError:
        pytest.skip("FMP returned no transcript for AAPL 2024 Q4")
    assert transcript.ticker == "AAPL"
    assert transcript.provider == "fmp"
    assert len(transcript.turns) > 0
