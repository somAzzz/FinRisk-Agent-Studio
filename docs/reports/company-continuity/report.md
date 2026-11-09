# Company continuity: Südzucker AG

Two independent annual PDFs resolve to **de-mannheim-hrb-42**. The issuer's consolidated-accounting note identifies the registry court and HRB number in both originals. The share tables independently disclose SZU, the qualified Reuters symbol SZUG.DE, and equity ISIN DE0007297004. The registry identifies the entity; the listings identify instruments. Bond identifiers on the same pages are not issuer keys.

| Original | Publication | Full PDF pages processed | Legal identity | Share listing | Segment table |
|---|---|---:|---:|---:|---:|
| [FY 2024/25](https://www.suedzuckergroup.com/sites/default/files/2025-05/Suedzucker_Geschaeftsbericht_2024%E2%80%9325.pdf) | 15 May 2025 | 259 | PDF 187 | PDF 18 | PDF 3 |
| [FY 2025/26](https://www.suedzuckergroup.com/sites/default/files/2026-05/Suedzucker_Geschaeftsbericht_2025-26.pdf) | 21 May 2026 | 278 | PDF 205 | PDF 21 | PDF 6 |

**Observed movements, EUR million.** Each column comes from its own original. Both annual segment tables reconcile to group totals and the newer report independently repeats the older value. A conflicting comparative or an unmatched segment gets no change calculation. EBITDA and operating EBITDA were not treated as the same measure. The figures below describe movements and do not attribute them to any event.

| Segment | Revenue change | Operating result FY 2024/25 | Operating result FY 2025/26 | Result change |
|---|---:|---:|---:|---:|
| Sugar | −1,090 | −13 | −177 | −164 |
| Special products | −59 | 203 | 177 | −26 |
| CropEnergies | −166 | 22 | 37 | +15 |
| Starch | −44 | 36 | 21 | −15 |
| Fruit | +17 | 102 | 105 | +3 |
| Group | −1,342 | 350 | 163 | −187 |

**Two different evidence tests.** First, a new question was derived from the FY 2024/25 outlook alone, before looking at the later PDF. On 15 May 2025, the Sugar operating-result range (−200 to −100, PDF 58) had no actual. On 21 May 2026, the later report's exact annual measure, unit, segment and fiscal period matched; −177 is within the disclosed range. This verifies the numerical outcome only. It does not establish delivery performance, a price recovery, or the cause of the result.

Second, the three previously saved May 2026 questions retained their original task IDs. As of 8 October and 8 November the saved graph connected each question to passages in later publications via its own claims and review decisions. The Mercosur question had one checked entry; beet acreage/yields had three; starch pricing/margins had six page/verdict entries. These are retrieval and review records, not independent confirmations. In particular, [the July quarterly report, PDF 2](https://www.suedzuckergroup.com/sites/default/files/2026-07/Q1_2026-27_EN.pdf#page=2) was a wrong citation for the starch question. All three answers and fulfilment states remain **unknown**. The May replay contains none of the July or October evidence. The November replay does not duplicate the October review paths.

**Briefs and journal.** New work launched from a verified issuer carries its company ID. The server checks that the selected ticker belongs to a disclosed listing. Legacy bare tickers do not attach automatically. A qualified legacy ticker requires consistent dated disclosures bracketing the record using only information available by the selected cutoff. A conflicting resolved profile is excluded. The live saved sources contained no verified Südzucker FinRisk brief or journal entry for 8 November; the workspace shows those empty states. An isolated storage/API test exercised the existing brief and journal models with both positive and negative records. Those test records were not inserted into the real journal or presented as research findings.

**Scope.** The resolver recognizes explicit German issuer/registry disclosures and unique, checksum-valid LEIs in standard inline XBRL reporting contexts. Unsupported formats, conflicting IDs, different identifier schemes with no verified crosswalk, and company renamings without stable registration evidence are not joined by name. The outlook test implements a narrowly typed range contract, not a free-text inference engine. Existing records are not rewritten by the company view. Latest-only journal storage omits records edited after a replay date rather than showing later text as historical.

**Reproduction.** Run the following with the official full PDFs. The exporter verifies both original SHA-256 digests; the resulting two saved extracts reproduced byte-for-byte. No new OCR or LLM output is needed for this acceptance. The original tracking lane uses previously saved reviews.

```bash
.venv/bin/python -m scripts.company_continuity_case data/Suedzucker_Geschaeftsbericht_2024-25.pdf data/Suedzucker_Geschaeftsbericht_2025-26.pdf
.venv/bin/python -m pytest -q tests/test_company_continuity.py
```

[Machine-readable comparison, question paths, original URLs and hashes](acceptance.json) · [Browser verification](workspace.jpg)
