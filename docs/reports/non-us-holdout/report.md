# Novo Nordisk single-report holdout

**Eight pages missed 76 of the 78 relationships in the reviewed reference. Reading all 137 pages recovered 13 more relationships and still missed 63.** Non-US evidence discovery produced two historical UK regulatory paths in the frozen full-report run. A separate post-freeze test found two UK regulator decisions published after the annual report.

The only company-specific input to either frozen run was [Novo Nordisk’s 2025 Annual Report](https://www.novonordisk.com/content/dam/nncorp/global/en/investors/irmaterial/annual_report/2026/novo-nordisk-annual-report-2025.pdf). The issuer is Danish and operates in pharmaceuticals. The observation date was 8 November 2026. The company published the report on 4 February 2026. [Issuer publication notice](https://www.novonordisk.com/news-and-media/news-and-ir-materials/news-details.html?id=916485)

| Frozen arm | Unique supported predictions | TP | FP | FN | Precision | Recall | Verified non-US event paths |
|---|---:|---:|---:|---:|---:|---:|---:|
| Eight pages | 4 | 2 | 2 | 76 | 50.0% | 2.6% | 0 |
| All 137 pages | 23 | 15 | 8 | 63 | 65.2% | 19.2% | 2 |

Precision is the proportion of supported predictions in the reference. Recall is the proportion of reference relationships recovered. The eight pages were 89, 95, 6, 63, 17, 24, 55 and 51. Both arms used the same page decisions; the full arm reused these eight. Company legal suffixes, trademark signs, case and a trailing “segment” were normalized for scoring. Direction, role and endpoint types had to match. The full run contained 32 supported raw entries before normalization and five raw abstentions. The eight-page run had four supported entries and one abstention. The comparison measures the page budget on this report under the frozen page-level extractor. It does not estimate recall of the earlier Boeing run.

## Where the relationships were lost

The eight-page arm found both formal segments and zero correctly assigned product relationships. Of its 76 missed reference relationships, 71 had no object-disclosure page from the reference witness list in the selected eight; three had a witness page selected and produced no exact candidate; two products were proposed with the wrong subject. Witness lists record verified disclosures and can omit redundant mentions. The experimentally measured gain from reading the rest of the report is **13 additional true positives**, or 16.7 percentage points of recall.

The full run correctly assigned 13 products. For 61 remaining relationships the extractor saw an annotated page but did not propose the exact relation. Two products, Sogroya and Alhemo, were attached to a production heading. Six other false positives classified geographic sales areas as reporting segments. Note 2.2 on page 89 defines the two formal segments as *Obesity and Diabetes care* and *Rare disease*.

Page 25 explains much of the remaining gap. Its multi-column product overview lists drug families, brands and delivery devices; the full pipeline returned zero candidates for that page. Page 90 returned 15 candidates, reaching the per-window extraction limit. The limit can restrict output; this experiment does not assign an exact number of misses to the cap. Layout-aware extraction of portfolio tables and validation against the formal segment note are the next changes to test.

## Independent reference

Both predictions were hashed before annotation. A separate annotation process screened all 137 physical pages using layout-preserving text, its own instructions and no predictions, page ranking, graph or external results. It proposed 82 provisional mentions. A subsequent source-only review used the rendered product table, the formal segment definitions and the sales notes to correct false segments and add missed products. The final 78 unique relationships were sealed before opening either prediction. The reference includes both individually named products and explicitly reported product families. It excludes unallocated group relationships, approval-only pipeline candidates and sales regions as evidence of a physical operating presence.

The first annotation pass used the same local model in an isolated context. The source-only review was performed by the coding assistant. No independent human annotation or inter-rater agreement statistic is claimed. This is a reference-relative measurement for one issuer and the declared relation types. [Reference and witness pages](reference.json) · [Complete scoring ledger](scores.json)

## External evidence and graph readback

The frozen eight-page graph had no verified product reachable from a formally reported segment, so it generated no external research task. The full graph chose Ozempic, Wegovy and Tresiba. One official roundup retrieved for Ozempic contained an eligible notice about NovoRapid, another product already present in the annual graph. Only non-US sources could be admitted. In the following table, the historical notices establish what the regulator published at the time; the later status of those shortages is unknown.

| Stage | Official publication | Reviewed graph path | Finding |
|---|---|---|---|
| Frozen | [MHRA, 29 April 2024](https://www.gov.uk/drug-safety-update/letters-and-medicine-recalls-sent-to-healthcare-professionals-in-march-2024) | Tresiba → Obesity and Diabetes care | The regulator listed a UK supply-shortage communication for the 100 U/mL presentation. The 200 U/mL item concerned a medication error. |
| Frozen | [MHRA, 24 June 2025](https://www.gov.uk/drug-device-alerts/mhra-safety-roundup-june-2025) | NovoRapid → Obesity and Diabetes care | The regulator listed a potential supply shortage for the specific PumpCart cartridge. |
| Post-freeze | [MHRA, 11 June 2026](https://www.gov.uk/government/news/first-glp-1-tablet-for-weight-loss-approved-in-the-uk) | Wegovy → Obesity and Diabetes care | The MHRA approved the semaglutide tablet for weight management under the conditions in its announcement. |
| Post-freeze | [MHRA, 3 July 2026](https://www.gov.uk/government/news/semaglutide-wegovy-approved-to-treat-form-of-liver-disease) | Wegovy → Obesity and Diabetes care | The MHRA approved the injectable presentation for a defined liver-disease indication in adults. |

The recent diagnostic reused the original machine-selected targets. It normalized trademark symbols and limited retrieval to the preceding 180 days. The first recent checks returned zero accepted paths. Selecting an index into complete original sentences, followed by a separate entailment check, returned the two dated decisions above. No external evidence link, known event or target-company map was injected. The recent decisions do not count toward the frozen result. UK official-source retrieval is demonstrated here; coverage outside this jurisdiction remains unmeasured.

Each accepted UK publication was rechecked against its archived bytes, URL path, publication date and decisive text. The segment connection was verified against annual-report page 90 and read back in Neo4j. The final view retains only independently matched annual edges, with no missed reference edge inserted. Trial false positives are retained as unverified relationships and removed from ordinary factual traversal. All four events have **unknown realized financial impact, unknown attributable amount and unknown contract fulfillment**. The reviewed graph identifies exposure, without a disclosed monetary allocation. [Reviewed graph and source spans](all-reviewed.json) · [Archived official originals](originals)

## Audit and reproduction

The [protocol](protocol.md) describes the frozen comparison. Re-score the [eight-page](eight-frozen.json) and [all-page](all-frozen.json) predictions against the [reviewed reference](reference.json). The [scores](scores.json) preserve the results for both arms. The post-freeze observations are documented above.

From the repository root, use the configured local LLM and Neo4j. The commands below show the data boundary between prediction, independent annotation and scoring.

```bash
python -m scripts.compare_exposure_coverage ANNUAL.pdf --output RUN
python -m scripts.label_report_relationships ANNUAL.pdf REFERENCE_QUEUE
# Review the queue against the PDF and seal the reference before inspecting RUN.
python -m scripts.score_exposure_coverage REFERENCE.json RUN SCORES.json
python -m scripts.recheck_recent_exposures RUN/all RECENT
```
