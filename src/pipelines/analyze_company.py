"""End-to-end MVP pipeline that analyses a single public company.

The pipeline glues together the data loaders, extraction agents, analysis
agents, opportunity discovery, and report generation. External dependencies
(SEC network, transcript providers, web search, Neo4j) are all best-effort:
failures degrade gracefully and never abort the demo run.

Running ``python -m src.pipelines.analyze_company --ticker DEMO
--offline-fixtures`` works without any API keys, using the JSON fixtures
under ``tests/fixtures/``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from src.agents.policy_geo_agent import PolicyGeoAgent
from src.agents.state import AgentState
from src.data.filing_fetcher import FilingFetcher, _build_filing_html_url
from src.pipelines.analyze_risks import analyze_company_risks
from src.pipelines.analyze_sentiment import analyze_management_sentiment
from src.pipelines.discover_opportunities import discover_opportunities
from src.pipelines.generate_report import generate_company_report
from src.schemas.claims import Claim
from src.schemas.evidence import Evidence
from src.schemas.filings import FilingMetadata, FilingRecord
from src.schemas.transcripts import Transcript

logger = logging.getLogger(__name__)

DEFAULT_FIXTURE_DIR = Path("tests/fixtures")


class AnalyzeCompanyArgs(BaseModel):
    """CLI args for the ``analyze_company`` pipeline.

    The model is closed (``extra="forbid"``) and is also used by the
    ``__main__`` block to validate the ``argparse`` namespace.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str
    year: int | None = None
    max_transcripts: int = 4
    max_web_results: int = 5
    write_graph: bool = False
    no_web: bool = False
    no_transcripts: bool = False
    output: str | None = None
    offline_fixtures: bool = False


# ---------------------------------------------------------------------------
# Fixture loaders (offline mode)
# ---------------------------------------------------------------------------


def _load_filing_fixture(path: Path) -> FilingRecord:
    """Load a :class:`FilingRecord` from a JSON fixture file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return FilingRecord.model_validate(payload)


def _load_transcript_fixture(path: Path) -> Transcript:
    """Load a :class:`Transcript` from a JSON fixture file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return Transcript.model_validate(payload)


def _load_web_results_fixture(path: Path) -> list[Evidence]:
    """Load a list of :class:`Evidence` from a JSON fixture file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        msg = f"web_results fixture must be a list, got {type(payload).__name__}"
        raise ValueError(msg)
    return [Evidence.model_validate(item) for item in payload]


def _load_offline_fixtures(
    fixture_dir: Path,
) -> tuple[list[FilingRecord], list[Transcript], list[Evidence]]:
    """Load the three demo fixtures and return filings/transcripts/evidence."""
    filings = [_load_filing_fixture(fixture_dir / "demo_filing.json")]
    transcripts = [
        _load_transcript_fixture(fixture_dir / "demo_transcript.json")
    ]
    web_evidence = _load_web_results_fixture(
        fixture_dir / "demo_web_results.json"
    )
    return filings, transcripts, web_evidence


# ---------------------------------------------------------------------------
# Live data fetchers (best-effort, with graceful degradation)
# ---------------------------------------------------------------------------


def _load_filings_live(
    ticker: str, year: int | None
) -> list[FilingRecord]:
    """Try to load filings from SEC, falling back to the HF EDGAR dataset."""
    # 1. Try SEC submissions first.
    filings: list[FilingRecord] = []
    try:
        from src.data.sec_client import SECClient
        from src.data.ticker_resolver import TickerResolver

        ident = TickerResolver().resolve(ticker)
        if ident is None:
            logger.info(
                "SEC live fetch skipped: unable to resolve %r", ticker
            )
        else:
            client = SECClient()
            try:
                metadata_list = client.get_submissions(ident.cik)
                recent = (
                    metadata_list.get("filings", {}).get("recent", {}) or {}
                )
                accession_numbers = recent.get("accessionNumber", []) or []
                forms = recent.get("form", []) or []
                filing_dates = recent.get("filingDate", []) or []
                primary_docs = recent.get("primaryDocument", []) or []
                fetcher = FilingFetcher(client)
                for idx in range(min(len(accession_numbers), 50)):
                    form = (forms[idx] if idx < len(forms) else "") or ""
                    if form.upper() not in {"10-K", "10-Q"}:
                        continue
                    try:
                        filing_date = date.fromisoformat(
                            filing_dates[idx]
                            if idx < len(filing_dates)
                            else ""
                        )
                    except ValueError:
                        continue
                    primary_doc = (
                        primary_docs[idx]
                        if idx < len(primary_docs)
                        else ""
                    )
                    metadata_obj = FilingMetadata(
                        cik=ident.cik,
                        accession_number=accession_numbers[idx],
                        form_type=form,
                        filing_date=filing_date,
                        report_date=None,
                        primary_document=primary_doc,
                        url=_build_filing_html_url(
                            accession_numbers[idx],
                            ident.cik,
                            primary_doc,
                        ),
                    )
                    try:
                        filing = fetcher.fetch_filing(metadata_obj)
                    except Exception as exc:  # noqa: BLE001
                        logger.info(
                            "Failed to download %s for %s: %s",
                            metadata_obj.accession_number,
                            ticker,
                            exc,
                        )
                        continue
                    filings.append(filing)
                    logger.info(
                        "SEC fetched %s for %s (filed %s)",
                        metadata_obj.form_type,
                        ticker,
                        metadata_obj.filing_date,
                    )
                    if (
                        year is not None
                        and filing_date.year == year
                    ):
                        break
            except Exception as exc:  # noqa: BLE001
                logger.info("SEC live fetch limited: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.info("SEC live fetch skipped: %s", exc)

    # 2. If SEC returned nothing, try defeatbeta-api's filing catalog.
    #    Defeatbeta requires no API key and usually covers more years than
    #    SEC's "recent" submissions endpoint; bodies still come from
    #    SECClient via FilingFetcher so we just feed it the catalog
    #    metadata. We use SEC's submissions API once to map accession
    #    numbers to primary documents (defeatbeta's URL omits the
    #    document filename).
    if not filings:
        try:
            from src.data.providers.defeatbeta import (
                fetch_filings_catalog_defeatbeta,
            )
            from src.data.sec_client import SECClient as _SECClient
            from src.data.ticker_resolver import TickerResolver

            catalog = fetch_filings_catalog_defeatbeta(
                ticker,
                form_types=["10-K", "10-Q"],
                limit=5,
            )
            if catalog:
                client = _SECClient()
                # Build accession_number -> primary_document map from
                # SEC's submissions JSON. The "recent" block carries
                # primaryDocument for up to the last ~1000 filings.
                primary_doc_by_accession: dict[str, str] = {}
                fallback_ident = TickerResolver().resolve(ticker)
                if fallback_ident is not None:
                    try:
                        sub_payload = client.get_submissions(
                            fallback_ident.cik
                        )
                        recent = (
                            sub_payload.get("filings", {}).get("recent", {})
                            or {}
                        )
                        accs = recent.get("accessionNumber", []) or []
                        docs = recent.get("primaryDocument", []) or []
                        for idx, acc in enumerate(accs):
                            if idx < len(docs) and docs[idx]:
                                primary_doc_by_accession[acc] = docs[idx]
                    except Exception as exc:  # noqa: BLE001
                        logger.info(
                            "SEC submissions lookup for catalog enrichment failed: %s",
                            exc,
                        )

                fetcher = FilingFetcher(client)
                for metadata_obj in catalog:
                    # Enrich the catalog metadata with the SEC-supplied
                    # primary document; without it, SECClient.get_filing_html
                    # cannot construct the body URL.
                    primary_doc = primary_doc_by_accession.get(
                        metadata_obj.accession_number, ""
                    )
                    if not primary_doc:
                        logger.info(
                            "defeatbeta catalog entry %s has no primary_document; skipping",
                            metadata_obj.accession_number,
                        )
                        continue
                    enriched_metadata = metadata_obj.model_copy(
                        update={"primary_document": primary_doc}
                    )
                    try:
                        filing = fetcher.fetch_filing(enriched_metadata)
                    except Exception as exc:  # noqa: BLE001
                        logger.info(
                            "Failed to download %s via defeatbeta catalog: %s",
                            enriched_metadata.accession_number,
                            exc,
                        )
                        continue
                    # Tag provenance so downstream consumers can see the
                    # catalog source — the FilingRecord itself still has
                    # source="sec" because the body came from SEC.
                    if isinstance(filing.metadata, dict):
                        filing.metadata["catalog_source"] = "defeatbeta"
                    filings.append(filing)
                    if (
                        year is not None
                        and enriched_metadata.filing_date is not None
                        and enriched_metadata.filing_date.year == year
                    ):
                        break
        except Exception as exc:  # noqa: BLE001
            logger.info("defeatbeta catalog fetch skipped: %s", exc)

    # 3. Fall back to the Hugging Face EDGAR corpus (streaming).
    if not filings:
        try:
            from src.data.edgar_hf import EdgarCorpusLoader

            loader = EdgarCorpusLoader()
            iterator = loader.iter_filings(limit=5)
            for filing in iterator:
                if ticker and ticker.upper() not in {
                    (filing.ticker or "").upper(),
                    filing.cik,
                }:
                    # The HF loader does not currently key by ticker; accept
                    # the first available filing as a stand-in so the demo
                    # can still produce output.
                    pass
                if year is not None and filing.year is not None:
                    if filing.year != year:
                        continue
                filings.append(filing)
                if len(filings) >= 1:
                    break
        except Exception as exc:
            logger.warning("HF EDGAR loader failed: %s", exc)

    return filings


def _load_transcripts_live(
    ticker: str, max_transcripts: int
) -> list[Transcript]:
    """Try to load earnings-call transcripts; skip providers without keys."""
    transcripts: list[Transcript] = []
    if max_transcripts <= 0:
        return transcripts

    # Try defeatbeta (free, no key) first, then FMP and Alpha Vantage.
    # Any provider missing its dependency is silently skipped.
    for provider_name in ("defeatbeta", "fmp", "alpha_vantage"):
        if provider_name == "fmp" and not os.environ.get("FMP_API_KEY"):
            continue
        if provider_name == "alpha_vantage" and not os.environ.get(
            "ALPHA_VANTAGE_API_KEY"
        ):
            continue
        try:
            if provider_name == "fmp":
                from src.data.providers.fmp import FMPProvider

                provider = FMPProvider()
            elif provider_name == "alpha_vantage":
                from src.data.providers.alpha_vantage import (
                    AlphaVantageProvider,
                )

                provider = AlphaVantageProvider()
            else:
                from src.data.providers.defeatbeta import DefeatBetaProvider

                provider = DefeatBetaProvider()
            metas = provider.list_transcripts(ticker)
            for meta in metas[:max_transcripts]:
                try:
                    transcripts.append(
                        provider.get_transcript(
                            ticker, meta.year, meta.quarter
                        )
                    )
                except Exception:
                    continue
        except Exception as exc:
            logger.info(
                "Transcript provider %s skipped: %s", provider_name, exc
            )
            continue
        if transcripts:
            break

    return transcripts


def _load_web_evidence_live(
    ticker: str, max_results: int
) -> list[Evidence]:
    """Run a web search for the ticker; returns ``[]`` on any failure."""
    try:
        from src.tools.search_router import SearchRouter, to_evidence
    except Exception as exc:
        logger.info("SearchRouter unavailable: %s", exc)
        return []
    try:
        router = SearchRouter()
        response = router.search(
            query=f"{ticker} recent news risks opportunities",
            max_results=max_results,
        )
    except Exception as exc:
        logger.info("Web search failed: %s", exc)
        return []

    evidence: list[Evidence] = []
    for index in range(min(max_results, len(response.results))):
        try:
            evidence.append(to_evidence(response, result_index=index))
        except Exception:
            continue
    return evidence


# ---------------------------------------------------------------------------
# Graph writer (best-effort, never fatal)
# ---------------------------------------------------------------------------


def _maybe_write_graph(
    claims: list[Claim],
    entities: list,
    relations: list,
    evidence: list[Evidence],
) -> str:
    """Attempt to write ``claims``/``entities``/``relations`` to Neo4j.

    Returns a short human-readable status string. Any error (no Neo4j,
    connection refused, etc.) is swallowed because the graph layer is
    optional in the MVP.
    """
    if not os.environ.get("NEO4J_URI"):
        return "skipped (NEO4J_URI not set)"

    try:
        from src.graph.client import Neo4jClient
        from src.graph.writer import GraphWriter
    except Exception as exc:
        return f"skipped (graph module unavailable: {exc})"

    try:
        client = Neo4jClient()
        writer = GraphWriter(client)
    except Exception as exc:
        return f"skipped (Neo4j not reachable: {exc})"

    try:
        from src.agents.extraction_agent import ExtractionResult

        result = ExtractionResult(
            entities=entities,
            relations=relations,
            claims=claims,
            evidence=evidence,
        )
        writer.write_extraction_result(result)
        return "written"
    except Exception as exc:
        return f"failed ({exc})"


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------


def analyze_company(args: AnalyzeCompanyArgs) -> str:
    """Run the end-to-end MVP pipeline and return the Markdown report.

    The function never raises on external-dependency failures; everything
    that can fail is wrapped in ``try/except`` and the rest of the pipeline
    continues with whatever data is available.
    """
    ticker = args.ticker.upper()
    state_notes: list[str] = []

    # 1. Collect raw evidence.
    if args.offline_fixtures:
        filings, transcripts, web_evidence = _load_offline_fixtures(
            DEFAULT_FIXTURE_DIR
        )
    else:
        live_notes: list[str] = []
        try:
            filings = _load_filings_live(ticker, args.year)
        except Exception as exc:
            live_notes.append(f"live filings unavailable: {exc}")
            filings = []
        if args.no_transcripts:
            transcripts = []
        else:
            try:
                transcripts = _load_transcripts_live(
                    ticker, args.max_transcripts
                )
            except Exception as exc:
                live_notes.append(f"live transcripts unavailable: {exc}")
                transcripts = []
        if args.no_web:
            web_evidence = []
        else:
            try:
                web_evidence = _load_web_evidence_live(
                    ticker, args.max_web_results
                )
            except Exception as exc:
                live_notes.append(f"live web evidence unavailable: {exc}")
                web_evidence = []
        state_notes.extend(live_notes)

    # 2. Build a single AgentState that downstream agents can mutate.
    company_name = ticker
    if filings:
        company_name = filings[0].company_name or ticker
    elif transcripts:
        company_name = transcripts[0].company_name or ticker

    state = AgentState(
        goal=f"analyze {ticker}",
        ticker=ticker,
        company_name=company_name,
    )


    # 3. Run analysis pipelines. Each one is best-effort.
    all_claims: list[Claim] = []
    all_evidence: list[Evidence] = []

    # 2b. Run rule-based supply-chain extraction across all raw evidence so
    # the offline MVP produces populated Supply Chain Map sections even
    # without an LLM in the loop. This is a heuristic pass — a future LLM
    # structured-output pass can replace or augment it.
    try:
        from src.pipelines.rule_supply_chain import extract_supply_chain_claims
        from src.schemas.filings import FilingRecord  # noqa: F401
        from src.schemas.transcripts import Transcript  # noqa: F401

        pre_evidence: list[Evidence] = list(web_evidence)
        for filing in filings:
            for section, text in (filing.sections or {}).items():
                if not text:
                    continue
                pre_evidence.append(
                    Evidence(
                        evidence_id=(
                            f"{filing.accession_number or filing.cik}:{section}"
                        ),
                        source_type="sec_filing",
                        source_id=(
                            filing.accession_number
                            or f"{filing.cik}-{filing.form_type}"
                        ),
                        title=filing.company_name or filing.cik,
                        url=filing.url,
                        section=section,
                        quote=text,
                        retrieved_at=datetime.now(UTC),
                        confidence=0.9,
                        metadata={
                            "cik": filing.cik,
                            "ticker": filing.ticker,
                            "form_type": filing.form_type,
                        },
                    )
                )
        for tx in transcripts:
            for idx, turn in enumerate(tx.turns):
                pre_evidence.append(
                    Evidence(
                        evidence_id=f"{tx.transcript_id}:turn{idx}",
                        source_type="transcript",
                        source_id=tx.transcript_id or "",
                        title=tx.title,
                        url=tx.url,
                        section=turn.section,
                        speaker=turn.speaker,
                        quote=turn.text,
                        retrieved_at=(
                            tx.published_at or datetime.now(UTC)
                        ),
                        confidence=0.85,
                        metadata={
                            "role": turn.role,
                            "ticker": tx.ticker,
                        },
                    )
                )
        supply_claims = extract_supply_chain_claims(pre_evidence)
        all_evidence.extend(ev for c in supply_claims for ev in c.evidence)
        all_claims.extend(supply_claims)
        logger.info(
            "rule_supply_chain emitted %d claims", len(supply_claims)
        )
    except Exception as exc:
        logger.warning("rule_supply_chain extraction failed: %s", exc)

    all_entities: list = []
    all_relations: list = []

    try:
        risk = analyze_company_risks(ticker, filings, transcripts, web_evidence)
        all_claims.extend(risk.risks)
        all_evidence.extend(risk.evidence)
    except Exception as exc:
        logger.warning("risk pipeline failed: %s", exc)

    try:
        sentiment = analyze_management_sentiment(
            ticker, transcripts, mda_sections=[]
        )
        all_claims.extend(sentiment.claims)
    except Exception as exc:
        logger.warning("sentiment pipeline failed: %s", exc)

    try:
        policy_geo = PolicyGeoAgent()
        policy_geo.run(state)
        all_claims.extend(state.claims)
        all_evidence.extend(state.evidence)
        all_entities.extend(state.entities)
        all_relations.extend(state.relations)
    except Exception as exc:
        logger.warning("policy_geo agent failed: %s", exc)

    # Make sure all collected evidence rows flow into the state too (the
    # report agent needs the full evidence list, not just the policy_geo
    # subset).
    state.evidence.extend(web_evidence)
    state.claims.extend(all_claims)
    # Deduplicate evidence by ``evidence_id`` while preserving order.
    seen: set[str] = set()
    deduped_evidence: list[Evidence] = []
    for ev in all_evidence:
        if ev.evidence_id in seen:
            continue
        seen.add(ev.evidence_id)
        deduped_evidence.append(ev)
    state.evidence.extend(deduped_evidence)

    # 4. Opportunity discovery.
    try:
        hypotheses = discover_opportunities(ticker, state.claims, state.evidence)
    except Exception as exc:
        logger.warning("opportunity pipeline failed: %s", exc)
        hypotheses = []

    # 4b. Critic pass — drop claims without evidence and lower
    # overconfident high-confidence / low-evidence claims. This is the
    # last gate before the report is rendered so the body only asserts
    # what the evidence actually supports.
    try:
        from src.agents.critic import CriticAgent

        # Update state.claims with the critic's filtered list before
        # the report agent reads it.
        critic_state = AgentState(
            goal=f"analyze {ticker}",
            ticker=ticker,
            company_name=company_name,
        )
        critic_state.claims = list(all_claims)
        critic_state.evidence = list(deduped_evidence)
        CriticAgent().run(critic_state)
        all_claims = list(critic_state.claims)
    except Exception as exc:  # noqa: BLE001
        logger.warning("critic agent failed: %s", exc)

    # 5. Generate the Markdown report.
    report = generate_company_report(
        ticker=ticker,
        hypotheses=hypotheses,
        claims=state.claims,
        evidence=state.evidence,
    )

    # 6. Optional graph write.
    if args.write_graph:
        status = _maybe_write_graph(
            state.claims, all_entities, all_relations, state.evidence
        )
        report = f"{report}\n\n_Graph write: {status}_\n"

    # 7. Optional file output.
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")

    return report


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="analyze_company",
        description=(
            "Run the FinText-LLM MVP pipeline against a single ticker. "
            "Use --offline-fixtures to bypass all network calls."
        ),
    )
    parser.add_argument("--ticker", required=True, help="Stock ticker symbol")
    parser.add_argument(
        "--year", type=int, default=None, help="Filing year (optional)"
    )
    parser.add_argument(
        "--max-transcripts", type=int, default=4,
        help="Maximum number of transcripts to fetch (default: 4)",
    )
    parser.add_argument(
        "--max-web-results", type=int, default=5,
        help="Maximum number of web search results (default: 5)",
    )
    parser.add_argument(
        "--write-graph", action="store_true",
        help="Attempt to write extraction output to Neo4j",
    )
    parser.add_argument(
        "--no-web", action="store_true",
        help="Skip the web search step",
    )
    parser.add_argument(
        "--no-transcripts", action="store_true",
        help="Skip the transcript fetch step",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Write the report to this path instead of stdout",
    )
    parser.add_argument(
        "--offline-fixtures", action="store_true",
        help="Use JSON fixtures under tests/fixtures/ instead of live data",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    raw = parser.parse_args(argv if argv is not None else sys.argv[1:])
    args = AnalyzeCompanyArgs.model_validate(vars(raw))
    report = analyze_company(args)
    if not args.output:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
