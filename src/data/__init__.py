"""Data loading modules for FinText-LLM."""

from src.data.edgar_hf import EdgarCorpusLoader
from src.data.filing_fetcher import FilingFetcher
from src.data.loader import EdgarDataset
from src.data.providers.alpha_vantage import AlphaVantageProvider
from src.data.providers.fmp import FMPProvider
from src.data.sec_client import (
    SECClient,
    SECClientError,
    SECHTTPError,
    SECNotFoundError,
    SECRateLimitError,
)
from src.data.transcripts import (
    TranscriptCache,
    TranscriptMeta,
    TranscriptNotFoundError,
    TranscriptProvider,
    TranscriptProviderConfigError,
    TranscriptProviderError,
    TranscriptRateLimitError,
    infer_role,
    infer_section,
)
from src.data.xbrl import CompanyFacts, FactValue, extract_metric
from src.schemas.filings import FilingMetadata, FilingRecord

__all__ = [
    "AlphaVantageProvider",
    "CompanyFacts",
    "EdgarCorpusLoader",
    "EdgarDataset",
    "FMPProvider",
    "FactValue",
    "FilingFetcher",
    "FilingMetadata",
    "FilingRecord",
    "SECClient",
    "SECClientError",
    "SECHTTPError",
    "SECNotFoundError",
    "SECRateLimitError",
    "TranscriptCache",
    "TranscriptMeta",
    "TranscriptNotFoundError",
    "TranscriptProvider",
    "TranscriptProviderConfigError",
    "TranscriptProviderError",
    "TranscriptRateLimitError",
    "extract_metric",
    "infer_role",
    "infer_section",
]
