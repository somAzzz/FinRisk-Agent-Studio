from datetime import date

from src.annual_reports.audit import Claim, Passage, SpanCheck, Verdict, audit, audit_segment_edges
from src.annual_reports.documents import ocr_trigger
from src.annual_reports.segments import bullet_columns


def test_sparse_image_and_damaged_text_routes():
    assert ocr_trigger("Annual Report 2025 / page 19", True) == "sparse_text_over_image"
    assert ocr_trigger("Annual Report 2025 / page 19", False) is None
    assert ocr_trigger("Annual Report " + "\ufffd" * 12, False) == "damaged_text_layer"
    assert ocr_trigger("yearly sales and products " * 30, True) is None


def test_columns_retain_original_line_numbers_and_do_not_inherit_neighboring_titles():
    lines = ["   Division A               Division B"] + ["   • Item 1                 • Item 2"] * 5
    first, second = bullet_columns(lines)
    assert first[0] == "Division A" and second[0] == "Division B"
    assert second[4] == "• Item 2"


def test_unproven_relation_never_promoted_by_segment_definition():
    note = {"sha256": "abc", "definitions": {"tools": {"name": "Tools", "sha256": "abc", "page": 8, "quote": "Tools"}}}
    row = {"subject": "Tools", "subject_kind": "Segment", "relation": "PRODUCES", "status": "unknown"}
    assert audit_segment_edges([row], note)[0]["status"] == "unknown"
    misread = {**row, "subject": "Tools production", "status": "supported"}
    assert audit_segment_edges([misread], note)[0]["status"] == "unknown"


def test_formal_segment_claim_needs_eligible_note_even_when_local_judges_accept():
    p = Passage("e", "report", "abc", "2025-01-01", 8, "Tools markets drills.")
    c = Claim(text=p.text, citation=p.id, kind="observation", topic="operations", scope="Tools")

    def judge(model, *args):
        if model is Verdict:
            return Verdict(
                status="supported", reason="Exact", quote=p.text, evidence_id=p.id, direct=True, fulfillment="unknown"
            )
        return SpanCheck(
            formal_segments_claimed=["Tools"],
            every_clause_supported=True,
            answers_named_scope=True,
            explanation="Exact",
        )

    proof = {"name": "Tools", "sha256": "abc", "page": 9, "quote": "The reportable segments are Tools and Parts."}

    def note():
        return {"definitions": {"tools": proof}}

    for when, expected in [("2026-01-01", "insufficient"), ("2025-01-01", "supported")]:
        n = Passage("n", "report", "abc", when, 9, proof["quote"])
        res = audit(c, {"e": p, "n": n}, date(2025, 6, 1), llm=judge, note_loader=note)
        assert res["status"] == expected


def test_product_witness_requires_both_allocation_and_commercial_evidence():
    from src.annual_reports.segments import product_witness

    note = {"definitions": {"tools": {"name": "Tools", "aliases": {}}}, "context": "Tools: hardware."}
    row = {"subject": "Tools", "line": 1, "quote": "• Drill A"}
    assert product_witness(row, {0: "Hardware", 1: row["quote"]}, note, "Product overview")["allocation_line"] == 0
    assert not product_witness(row, {0: "Group", 1: row["quote"]}, note, "Product overview")
    assert not product_witness(row, {0: "Tools", 1: "Drill A will be introduced next year"}, note, "")


def test_catalog_heading_with_attached_footnote_selects_its_own_column():
    from src.annual_reports.segments import CATALOG

    assert CATALOG.search("Product overview1").group() == "Product overview"
    lines = ["   Tools                   Controls"] + ["   • Saw                   • Timer"] * 5
    lines.insert(3, "                                             adjacent prose")
    assert all(3 not in column for column in bullet_columns(lines))


def test_catalog_variant_grouping_preserves_distinct_models_and_unlabelled_column():
    from src.annual_reports.documents import Page
    from src.annual_reports.product_evidence import catalog_family_variants, catalog_rows

    doc_page = Page(2, None, "", "native")
    note = {"definitions": {"tools": {"name": "Tools"}, "medical": {"name": "Medical"}}, "context": ""}
    cols = [
        {0: "TOOLS", 1: "• Example® 30, alpha", 2: "• Example® 50, alpha"},
        {0: "Instruments", 1: "• Pump®", 2: "• Pen® 4", 3: "• Pen® 6"},
    ]
    a, b = [{"quote": q, "object": n} for q, n in [(cols[0][1], "Example® 30"), (cols[1][2], "Pen® 4")]]
    catalog_family_variants([a, b], cols)
    assert a["object"] == "Example®" and a["variant"] == "Example® 30"
    assert b["object"] == "Pen® 4"
    assert all(
        r["subject"] == "Tools" and r["object"] == "Example®"
        for r in catalog_rows(doc_page, note, cols, "Product overview")
    )


def test_completed_introduction_does_not_promote_comparator_or_future_candidate():
    from src.annual_reports.documents import Page
    from src.annual_reports.product_evidence import sentence_repairs

    page = Page(
        4,
        None,
        "New Alpha engine, which was introduced last year, is lighter than Beta. "
        "Gamma was planned for introduction next year.",
        "native",
    )
    rows = [
        {"object": name, "subject": "Engines", "allocation_quote": "Engines", "status": "unknown"}
        for name in ["Alpha", "Beta", "Gamma"]
    ]
    assert [r["object"] for r in sentence_repairs(page, rows, {})] == ["Alpha"]


def test_scope_enum_requires_corresponding_service_and_column_and_preserves_alias_proof():
    from src.annual_reports.documents import Page
    from src.annual_reports.product_evidence import model_scope_rows

    row = "Zone is a local service for vehicles.     Acme\u2019s L, P, R and S cabs"
    page = Page(
        7,
        None,
        "Scope. Zone is a local service for vehicles. Acme\u2019s L, P, R and S cabs.",
        "native",
        " " * row.index("Acme") + "Scope\n" + row,
        "layout",
    )
    note = {"definitions": {"vehicles": {"name": "Vehicles", "aliases": {"acme": {"page": 3, "quote": "Acme"}}}}}
    facts = model_scope_rows(page, note)
    assert [f["object"] for f in facts] == ["L cab", "P cab", "R cab", "S cab"]
    assert all(f["alias_evidence"]["page"] == 3 for f in facts)
    page.relationship_text = "Scope\n" + row
    assert model_scope_rows(page, note) == []


def test_cross_page_accessory_abstains_if_any_named_product_has_a_conflicting_or_missing_segment():
    from src.annual_reports.documents import Page
    from src.annual_reports.product_evidence import paired_device

    page = Page(5, None, "", "native")
    cells = ["• Adapter®, Alpha® and Beta®", "cartridge for use with the pump"]
    index = {"alpha": [{"segment": "Tools"}]}
    assert not paired_device(page, {"sales_brands": index}, cells, 0, "Product portfolio")
    index["beta"] = [{"segment": "Medical"}]
    assert not paired_device(page, {"sales_brands": index}, cells, 0, "Product portfolio")
    index["beta"] = [{"segment": "Tools"}]
    assert (
        len(paired_device(page, {"sales_brands": index}, cells, 0, "Product portfolio")[0]["cross_page_evidence"]) == 2
    )
