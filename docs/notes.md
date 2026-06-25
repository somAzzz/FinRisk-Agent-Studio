# Project Notes & Backups

## Note 1: Yahoo Finance Dataset (HuggingFace)

**Source:** https://huggingface.co/datasets/Joshua-Xia/yahoo-finance-data

### Overview
- **Size:** 100M < n < 1B records
- **License:** ODC-BY (Open Data Commons Attribution)
- **Format:** Parquet

### Data Tables (19 datasets)

| # | Table Name | Description |
|---|------------|-------------|
| 1 | `stock_profile` | Company details (address, industry, employees) |
| 2 | `stock_officers` | Executive info (name, title, pay, age) |
| 3 | `stock_summary` | Financial metrics (market cap, P/E, EPS) |
| 4 | `stock_tailing_eps` | Trailing EPS (TTM) |
| 5 | `stock_earning_calendar` | Upcoming earnings dates |
| 6 | `stock_revenue_estimates` | Analyst revenue forecasts |
| 7 | `stock_earning_estimates` | Analyst EPS estimates |
| 8 | `stock_historical_eps` | Historical earnings performance |
| 9 | `stock_statement` | Financial statements |
| 10 | `stock_prices` | Historical OHLCV data |
| 11 | `stock_dividend_events` | Dividend payments |
| 12 | `stock_split_events` | Stock split events |
| 13 | `exchange_rate` | Currency exchange rates |
| 14 | `daily_treasury_yield` | U.S. Treasury yields |
| 15 | `stock_earning_call_transcripts` | **Quarterly earnings call transcripts** |
| 16 | `stock_news` | Financial news articles |
| 17 | `stock_revenue_breakdown` | Revenue by segment/geography |
| 18 | `stock_shares_outstanding` | Shares outstanding data |
| 19 | `stock_sec_filing` | SEC filings (10-K, 10-Q, etc.) |

### Key: stock_earning_call_transcripts

Contains full earnings call transcripts with:
- `symbol` - Stock ticker
- `fiscal_year` - Fiscal year
- `fiscal_quarter` - Fiscal quarter (1-4)
- `transcripts` - Array of {paragraph_number, speaker, content}

### How to Access

```python
# Direct DuckDB query
import duckdb

con = duckdb.connect()
con.execute("""
    SELECT * FROM
    'https://huggingface.co/datasets/Joshua-Xia/yahoo-finance-data/resolve/main/data/stock_earning_call_transcripts.parquet'
    WHERE symbol='AAPL'
    LIMIT 10
""")

# Or via Python API
# pip install defeatbeta-api
```

### Example: Get Earnings Call Transcripts

```python
import duckdb

con = duckdb.connect()

# Query earnings call transcripts for AAPL
result = con.execute("""
    SELECT symbol, fiscal_year, fiscal_quarter, len(transcripts) as para_count
    FROM read_parquet('https://huggingface.co/datasets/Joshua-Xia/yahoo-finance-data/resolve/main/data/stock_earning_call_transcripts.parquet')
    WHERE symbol = 'AAPL'
    ORDER BY fiscal_year DESC, fiscal_quarter DESC
    LIMIT 5
""").df()

print(result)
# Output: 77 paragraphs per transcript
```

**Note:** Full transcript content is in the `transcripts` array (STRUCT with paragraph_number, speaker, content)

---

> **Note (2026-06-25):** `defeatbeta-api` is still listed in `pyproject.toml`, but the active transcript path in FinRisk-Agent-Studio goes through `src/data/transcripts.py` + `src/data/providers/`. This HF dataset remains a viable bulk-source candidate if `defeatbeta-api` coverage is ever insufficient.
