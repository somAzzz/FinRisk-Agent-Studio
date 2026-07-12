# Product Design QA — FinRisk Agent Studio multi-page redesign

Source visual truth: `docs/current/product-redesign-2026-07-12/company-workspace-target.png`
Exact-size implementation: `docs/current/product-redesign-2026-07-12/verification/overview-reference-viewport-current.jpg`
Source comparison viewport: 1487 × 1058
Route verification viewports: 1440 × 1024 desktop; 390 × 844 mobile
State: coherent offline AAPL product fixture

## Result

- No open P0, P1 or P2 design, usability, accessibility or core-interaction findings.
- Overview was measured against the source at the source image's exact 1487 × 1058 viewport and reviewed with both images in the same comparison input.
- All ten routes retain desktop and mobile screenshots in `docs/current/product-redesign-2026-07-12/verification/`.
- Final build and test gate: `npm run build` passed; 18 test files and 76 tests passed.
- Browser console: no warnings or errors beyond Vite/React development informational messages.

## Source-fidelity findings

- Global frame matches the target: 232px graphite navigation, 140px company header, local company tabs, light reading canvas, thin neutral dividers and restrained elevation.
- Overview geometry now tracks the source closely: the main card begins at x=248, the decision brief begins at y≈212, the risk/evidence split is approximately 776/426px, and Technical trace is visible in the source-height viewport.
- The four-column decision brief, six-row risk ledger, rank colors, seven-day trend marks, 78/100 evidence donut, 62/23/10/5 legend, evidence counts and freshness row reproduce the target's hierarchy and density.
- Header copy and state match the target: Apple identity, industry/Nasdaq context, July 12 update time, amber “Partially available” health and a single teal Run update action.
- Product language is normalized; raw backend identifiers such as `supply_chain` are not exposed in decision-critical positions.
- Apple and interface glyphs come from installed icon libraries; no drawn placeholders or emoji are used as product assets.

## Multi-page product review

| Route | Visual and product outcome | Core interaction verified |
|---|---|---|
| Today | Clear daily queue, status strip, one review item and recent activity | Review, Start research, route to runs |
| Overview | Source-faithful decision brief and evidence/risk hierarchy | View all risks, Source freshness → Evidence, Run update drawer, Technical trace |
| Risks | Ranked ledger and selected-risk detail make priority and transmission explicit | Risk selection and evidence navigation |
| Financials | Standardized KPI strip, lineage table and warnings separate reported from derived values | Warning disclosure and metric inspection |
| Valuation | Assumptions are visually separated from evidence and results | Scenario, sensitivity, market multiple and DCF calculations |
| Management | Period comparison, tone KPIs and topic changes form one review path | Compare calls using coherent fixture |
| Supply Chain | Controls, Sankey, node intelligence and evidence warning are visible together | Fixture run, node selection and expansion |
| Evidence | Release gate, claim coverage, source inventory and graph detail support review | Technical detail disclosure and evidence navigation |
| Research Runs | Run history, controls and execution detail use an auditable three-column layout | Run Agent, completed state, Tool Trace, candidate approval and human review |
| Journal | Thesis memory and point-in-time workflow are populated rather than empty/error states | Save thesis, create snapshot, compare peers, generate review draft, scan/queue actions |

## Responsive and accessibility review

- At 390px the primary navigation becomes a 40px menu control; opening it exposes all main routes plus Activity and Runtime settings.
- Company identity, health and Run update stack without overlap. Company tabs remain horizontally scrollable and retain an active underline.
- Decision columns, risk detail, financial KPIs, valuation assumptions, management inputs, evidence KPIs, Runs and Journal layouts collapse to one readable column.
- No captured route shows document-level horizontal clipping, fixed-panel obstruction or an unreachable primary action.
- Active routes use `aria-current`; errors use `role=alert`; the skip link targets the active main landmark; drawers expose dialog labels, Escape dismissal, focus entry and body scroll lock.
- Buttons preserve visible focus styling and minimum mobile action height. Reduced-motion support remains present.

## Fixed during final QA

- Route changes now reset the viewport to the top, preventing a new screen from inheriting the previous screen's scroll position.
- Static Journal no longer calls an unavailable API. It uses consistent thesis, watchlist, reminder, snapshot, change and queue fixtures, and its save/compare/review actions mutate the demo state.
- Static Research Runs no longer produces a 502. Run Agent creates a completed timeline with source-backed tool events, evidence candidates and review actions.
- Overview evidence score, health state, timestamp, grid proportions, row density, freshness control and Technical trace position were calibrated against the exact source viewport.
- The route-level lazy split remains in place; the main bundle stays below the previous 500kB warning threshold.

## Verification artifacts

- Exact source viewport: `overview-reference-viewport-current.jpg`
- Desktop/mobile pairs: `today-*`, `overview-*`, `risks-*`, `financials-*`, `valuation-*`, `management-*`, `supply-chain-*`, `evidence-*`, `runs-*`, `journal-*` with the `-current.jpg` suffix.
- Completed agent-run state: `runs-desktop-interaction.jpg`

## Focused QA — Research Runs and Journal redesign

Source visual truth: `docs/current/product-redesign-2026-07-12/research-journal-redesign-audit/01-company-reference.jpg`
Implementation screenshots: `04-runs-after-desktop.jpg`, `05-journal-after-desktop.jpg`, `06-runs-after-mobile.jpg`, `07-journal-after-mobile.jpg`
Viewport: 1440 × 1024 desktop; 390 × 844 mobile
State: AAPL coherent static fixture, completed agent run with one pending analyst judgment, active thesis with one scheduled review

### Findings

- No open P0/P1/P2 findings.
- Typography: the same humanist sans hierarchy and restrained monospace metadata used by Company now carries Runs and Journal. Headings, labels, body text and long thesis content wrap without clipping.
- Spacing and layout rhythm: both pages use the same 32px desktop canvas, 16px section rhythm, 8px surfaces and thin dividers as Company. Runs prioritizes Run brief before the audit grid; Journal prioritizes Journal brief before the thesis/cycle split.
- Colors and tokens: evidence teal, diligence amber and risk red retain one semantic meaning across all three surfaces. There are no new ornamental gradients or generic shadow stacks.
- Image and icon fidelity: these are data-product screens without raster imagery. All visible icons come from the existing Lucide/react-icons families; no placeholder art, emoji, CSS illustrations or handcrafted SVGs were introduced.
- Copy and content: configuration, provenance and archive language is secondary; primary copy answers trust, evidence, diligence and thesis questions in analyst language.
- Responsive behavior: at 390px Runs moves history below the active run and keeps the brief in a 2×2 grid; Journal keeps its brief 2×2 so the active thesis enters the first viewport. No primary action is horizontally clipped.
- Interaction states: run setup opens/closes; Run Agent completes; candidate and human approval update accepted/review counts; thesis composer saves; snapshot and review draft flows complete.
- Browser console: no warning/error in the final Runs and Journal interaction sessions.

### Comparison history

- Earlier P1: Runs gave persistent configuration equal or greater weight than execution trust and review. Fix: collapsed configuration plus four-cell Run brief and dedicated human-judgment rail. Post-fix evidence: `04-runs-after-desktop.jpg` and `06-runs-after-mobile.jpg`.
- Earlier P1: Journal foregrounded an empty six-field form instead of the active thesis. Fix: Journal brief, Thesis spine and collapsed composer. Post-fix evidence: `05-journal-after-desktop.jpg` and `07-journal-after-mobile.jpg`.
- Earlier P2: mobile Runs stacked history before the current run; mobile Journal stacked four brief cells into a long wall. Fix: reordered active run before history and used 2×2 summary grids. Post-fix evidence: mobile artifacts above.
- Earlier P2: review controls visually ran together and the same candidate was counted twice through candidate + human-review records. Fix: deduplicated review IDs and used full-width paired actions.

Focused crops were not required: the 1440px screenshots keep the dense trace, review controls and thesis details readable at native resolution, and the matching 390px captures cover the responsive state directly.

final result: passed
