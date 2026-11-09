# Novo Nordisk catalog evidence and TRATON regression

Four previously unresolved Novo Nordisk relationships now have enough evidence to connect them to **Obesity and Diabetes care**. The remaining 18 catalog names have a page citation and an explicit unknown segment. No issuer name, product mapping, reference alias or target page is supplied to the extractor. The named targets appear in the evaluation only.

| Full report | Pages | Previously correct | Now correct / reference | Recall | Precision | False positives |
|---|---:|---:|---:|---:|---:|---:|
| Novo Nordisk | 137 | 54 | 58/76 | 71.1% → 76.3% | 58/58 | 0 |
| TRATON | 433 | 14 | 14/14 | 100% → 100% | 14/14 | 0 |

All 68 previously correct directed relationships were retained individually. The 18 abstentions remain in the recall denominator. Zero false positives means zero against the two unchanged reference sets. These were known reports used for development and regression; this is not an estimate for unseen issuers.

## Why each relationship passed

| Catalog item | Evidence from the report | What the evidence establishes |
|---|---|---|
| Single Dose Device | Page 25 names the device in the Wegovy entry under **Obesity delivery systems**, in the obesity business section. Page 89 assigns obesity to the formal segment. Page 90 reports positive Wegovy sales in that segment. | The segment markets a product with this named device. The device has no separate sales amount in this chain. |
| Pre-filled delivery systems | The middle catalog column on page 25 lists **FlexTouch** as a member and also pairs it with **Ozempic**. A separately verified entry in the labelled obesity column pairs FlexTouch with Saxenda. Page 89 defines the formal segment and page 90 reports Ozempic in its sales table. | At least one member establishes segment participation in the family. This does not allocate FlexPen, InnoLet, or the entire family’s revenue to that segment. |
| Oral antidiabetic agents | Page 25 uses the term as a commercial class heading with a branded entry beneath it. Page 89 names diabetes in the segment’s therapy scope. The reviewer checked that “antidiabetic” designates treatment of that condition. | The segment markets this treatment class. No particular molecule’s indication or sales are inferred. |
| NovoNorm | Page 25 lists NovoNorm as the primary brand immediately beneath **Oral antidiabetic agents**, before the next heading, **Glucagon**. The same page 89 scope applies. | The combination of a commercial brand entry and its verified class supports the segment link. The following Glucagon entries do not inherit that classification. |

The rendered catalog on page 25 was also checked visually. The middle list has no repeated business heading; the patent table to the right is not evidence of segment allocation. The term `PRODUCES` is the project's existing graph relation for a commercial product or family. Here it establishes commercial participation; it does not identify a manufacturing plant, exclusivity or attributable profit.

## What stayed unknown

| Catalog grouping on page 25 | Endpoints with no confirmed formal segment |
|---|---|
| Pre-filled delivery systems | FlexPen; InnoLet |
| Durable delivery systems | Durable delivery systems; NovoPen 6; NovoPen 5; NovoPen 4; NovoPen Echo Plus; NovoPen Echo |
| Other delivery systems | Penfill |
| Glucagon | Glucagon; GlucaGen; Hypokit; Zegalogue |
| Needles | Needles; NovoFine Plus; NovoFine; NovoTwist; NovoFine AutoCover |

Each of these 18 has its own unallocated record; none relies on simply being absent from extraction. A catalog citation identifies a mention, not a formal segment. The route check uses the report's verified segment definitions and the graph's production routing function: all four new targets are reachable and none of the 18 unknown endpoints is reachable.

## Rules and verification

The extractor builds bounded groups within physical columns. It can propose an unregistered device alongside a sales-verified host, a family with an independently allocated listed member, or a therapy class with an unambiguous condition in the segment note. In the last case it can also propose a primary brand explicitly listed under that heading. Each proposal starts as unknown. A separate model call reviews the evidence, and the formal-note check must also pass. The English naming and grammatical patterns are deliberately narrow; other languages and catalog layouts may still result in abstention.

The evaluation checked PDF fingerprints, full physical page sequences, the before/after sets of typed triples, the page and text of every accepted citation, the explicit unknown entries, and negative controls. It replayed native and layout text and used OCR readback when needed. The two full runs took 57.8 s and 91.0 s respectively. The source replay verified 78 Novo and 17 TRATON supported page records; several page records can support the same unique relationship. Focused and related pipeline tests: **41 passed**. Synthetic cases cover conflicting segment sales, overlapping condition scopes, missing section headings, different columns, and neighboring products that must not inherit a family allocation.

[Acceptance criteria](protocol.md) · [Verification and evidence for every unresolved endpoint](verification.json) · [Full Novo output](novo-verified.json) · [Full TRATON output](traton-verified.json)

To replay the frozen findings against the original PDFs, place the matching reports at the two paths in the input manifest. Run the verifier with Poppler and the configured OCR service:

```bash
sha256sum -c docs/reports/segment-catalog/inputs.sha256
mkdir -p .cache/catalog-replay
cp docs/reports/segment-catalog/*-verified.json .cache/catalog-replay/
uv run --no-sync --env-file .env python -m scripts.verify_segment_catalog .cache/non-us-holdout/annual.pdf .cache/segment-regression/traton.pdf .cache/catalog-replay
cmp docs/reports/segment-catalog/verification.json .cache/catalog-replay/verification.json
```

The [implementation fingerprints](implementation.sha256) describe the original experiment. The annual-report audit has since moved to the shared Pydantic AI runtime. To measure a fresh extraction, run `scripts.regress_segment_products` for each PDF with a separate output directory and score those predictions with the same verifier.
