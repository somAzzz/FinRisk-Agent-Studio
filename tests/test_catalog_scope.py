from types import SimpleNamespace

from src.annual_reports.catalog_scope import catalog_bridges, unallocated_mentions


def note():
    return {
        "page": 9,
        "sha256": "abc",
        "definitions": {"medical": {"name": "Medical"}, "tools": {"name": "Tools"}},
        "context": "• Medical: asthma, viruses and allergies. • Tools: hardware.",
        "sales_brands": {
            "alpha": [
                {
                    "segment": "Medical",
                    "page": 10,
                    "sha256": "abc",
                    "quote": "Alpha® 7",
                    "allocation_quote": "Medical segment:",
                }
            ]
        },
    }


def generate(cols, model=None, verified=()):
    return catalog_bridges(
        SimpleNamespace(number=2),
        model or note(),
        [dict(enumerate(col)) for col in cols],
        "Product portfolio",
        verified,
    )


def test_condition_scope_is_local_unique_and_only_a_proposal():
    cols = [["Oral anti-parasitic treatments", "• Proto®, preparation", "Spares", "• Delta®"], ["• Gamma®"]]
    rows = generate(cols)
    assert not rows
    cols[0][0] = "Oral anti-asthma treatments"
    facts = generate(cols)
    assert [r["object"] for r in facts] == [cols[0][0], "Proto®"]
    assert all(r["status"] == "unknown" and r["cross_page_evidence"][0]["page"] == 9 for r in facts)
    n = note()
    n["context"] = n["context"].replace("hardware", "asthma")
    assert not generate(cols, n)
    assert not generate([["TOOLS", *cols[0]]])


def test_named_equipment_needs_consistent_sales_and_business_section():
    col = ["MEDICAL", "Delivery equipment", "• Alpha®, Metered Dose Adapter and", "Omega®"]
    assert [r["object"] for r in generate([col])] == ["Metered Dose Adapter"]
    assert not generate([col[1:]])
    n = note()
    n["sales_brands"]["alpha"].append({"segment": "Tools"})
    assert not generate([col], n)


def test_family_participation_never_allocates_other_entries_or_crosses_a_heading():
    col = ["Disposable systems", "• Pin®", "• Peer®", "• Alpha®, Pin®"]
    w = {
        "subject": "Medical",
        "object": "Pin®",
        "quote": "• Beta®, Pin®",
        "allocation_quote": "MEDICAL",
        "evidence_rule": "co-listed catalog item",
        "status": "supported",
    }
    assert [r["object"] for r in generate([col], verified=[w])] == ["Disposable systems"]
    assert not generate([col], verified=[{**w, "status": "unknown"}])
    assert not generate([col[:3], col[3:]], verified=[w])
    assert not generate([[*col[:3], "New family", col[3]]], verified=[w])
    abstained = unallocated_mentions(SimpleNamespace(number=2), note(), [dict(enumerate(col))], "Product overview", [w])
    assert any(r["object"] == "Peer®" for r in abstained)
    assert all(r["status"] == r["subject"] == "unknown" for r in abstained)
