# Boeing holdout acceptance

[English report](report.md) · [Machine-readable decisions and search trace](result.json) · [Offline verification](verification.json)

## Protocol and result

The test used a single 169-page 2025 annual report from the [issuer-designated report host](https://materials.proxyvote.com/Approved/097023/20260217/AR_625422/images/The_Boeing_Company-AR2025.pdf). The pipeline received the local PDF, an output directory and a graph connection. Company-specific mappings, event names, reference answers and external evidence URLs were absent from its inputs. The generic source adapters use web search and the US Federal Register catalogue. Model sampling can produce different candidates on another live run.

Of 15 candidate annual-report relationships in the accepted run, 12 passed review. All 12 are supported on physical PDF page 9, where the three reportable segments and their businesses are described. The claimed production links for the 777-9, the 777-8 Freighter and the Global Services training activity lacked sufficient support for the precise predicate in the selected passages. Their status is unknown. The system selected eight pages after text screening. These counts measure decisions on candidates, and do not establish whole-report recall.

Three original FAA notices connected specific 737 or 777 variants to the Commercial Airplanes segment. The two October notices have distinct document numbers and apply to different variants. Publication establishes the regulatory exposure. The record contains no verified company cost allocation, shipment interruption or quantified change in orders. The 787 question remained open. No accepted path established a particular supplier or customer contract.

## First-pass results and corrections

The first complete-report run produced 14 supported relationships out of 15 and zero external paths. Its catalogue-to-original comparison rejected a typographical difference between ASCII and printed dashes. The adapter now checks the exact normalized identifier and cuts off adjacent notices. A later run exposed a malformed catalogue response and another allowed dates from generated summaries to extend beyond the decisive quote. The accepted run handled catalogue failures per query and used extractive external facts. The provisional graph containing unverified summary details was retired. Every run started with the same annual PDF after an initial cover-only mirror file was discarded. No company relationship or event URL was added during repair.

The successful run is a post-repair test on the same company. The result demonstrates automatic path construction for this issuer. Coverage of other industries, languages, regulators and named counterparties remains unmeasured. Some generated general web queries even included a stale year. The three accepted observations came from dated registry results. The blind route currently leaves all monetary attribution unknown.

## Reproduction

Use the existing configured LLM and Neo4j instance. The live command discovers the graph again. The verifier checks the frozen accepted run against the original bytes without a model or search call for this native-text PDF.

```bash
python main.py discover-exposures .cache/blind-input/annual-2025.pdf \
  --neo4j --output .cache/blind-run/new-run

python -m scripts.verify_blind_exposure \
  .cache/blind-input/annual-2025.pdf .cache/blind-run/accepted
```

The saved JSON identifies the dated Neo4j scope under `graph.scope`. Within that scope, trace an event over `CONCERNS` to the product, then back over `PRODUCES` to the segment and `HAS_SEGMENT` to the company. The relations carry provenance, source hash, physical page and a verbatim citation.
