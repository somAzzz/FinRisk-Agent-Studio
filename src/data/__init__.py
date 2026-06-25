"""Data loading modules for FinText-LLM."""

from src.data.edgar_hf import EdgarCorpusLoader
from src.data.filing_fetcher import FilingFetcher
from src.data.loader import EdgarDataset
from src.data.providers.alpha_vantage import AlphaVantageProvider
from src.data.providers.defeatbeta import (
    DefeatBetaProvider,
    fetch_filings_catalog_defeatbeta,
    fetch_financial_metrics_defeatbeta,
    fetch_revenue_breakdown_defeatbeta,
)
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
    "DefeatBetaProvider",
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
    "fetch_filings_catalog_defeatbeta",
    "fetch_financial_metrics_defeatbeta",
    "fetch_revenue_breakdown_defeatbeta",
    "infer_role",
    "infer_section",
]
