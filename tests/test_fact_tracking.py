from datetime import date

from src.annual_reports import tracking
from src.annual_reports.audit import Claim, Passage, SpanCheck, Verdict, audit, passages
from src.annual_reports.documents import Document, Page
from src.annual_reports.tracking import Plan, Proposal, Signal, Task, build_day


def test_future_passage_never_enters_judge_or_repair_and_delivery_is_unknown():
    current = Passage("today", "filing", "a", "2026-05-21", 1, "Production volumes declined locally.")
    future = Passage("tomorrow", "release", "b", "2026-10-08", 2, "ConfidentialFutureMarker")
    claim = Claim(
        text="The buyer received its order.",
        citation="today",
        kind="fulfillment",
        scope="the buyer",
        topic="downstream",
    )

    def misleading_judge(model, instruction, payload):
        assert "ConfidentialFutureMarker" not in str(payload)
        assert list(payload["evidence"]) == ["today"]
        return Verdict(
            status="supported",
            reason="similar",
            quote=current.text,
            evidence_id=current.id,
            direct=True,
            fulfillment="operating",
        )

    result = audit(claim, {p.id: p for p in (current, future)}, date(2026, 5, 21), llm=misleading_judge)
    assert result["status"] == "insufficient" and result["fulfillment"] == "unknown"
    assert result["follow_up"]["scope"] == "the buyer"


def test_positive_delivery_transition_and_alert_lineage(monkeypatch):
    start = date(2026, 5, 21)
    end = date(2026, 10, 8)
    seed = Document("seed", "a", [Page(1, None, "Customer pricing performance is a material exposure.", "native")])
    disclosure = Document(
        "update", "b", [Page(1, None, "Customer deliveries to Buyer A were interrupted in October.", "native")]
    )
    pool = passages(seed, start)
    task = Task(
        topic="downstream",
        scope="Buyer A",
        question="Were customer deliveries interrupted?",
        seed_id=next(iter(pool)),
        query="customer deliveries",
        terms="delivery customer",
        direct_evidence_needed="dispatch records",
        stop_condition="a dated update",
    )
    plan = Plan(tasks=[task])

    def fake(model, instructions, payload):
        if model is Proposal:
            pid = next(iter(payload["evidence"]))
            return Proposal(text="Customer deliveries to Buyer A were interrupted.", citation=pid, kind="fulfillment")
        if model is SpanCheck:
            return SpanCheck(every_clause_supported=True, answers_named_scope=True, explanation="Exact evidence")
        if model is Signal:
            return Signal(state="adverse", reason="Confirmed interruption")
        claim = payload["claim"]
        quote = payload["evidence"][claim["citation"]]["passage"]
        return Verdict(
            status="supported",
            reason="Reported by issuer",
            quote=quote,
            evidence_id=claim["citation"],
            direct=True,
            fulfillment="interrupted",
        )

    monkeypatch.setattr(tracking, "structured", fake)
    monkeypatch.setattr(tracking, "audit", lambda c, p, d, **kw: audit(c, p, d, llm=fake, **kw))
    docs = [(seed, start), (disclosure, end)]
    first = build_day(plan, docs, start, None)
    assert first["tasks"][0]["fulfillment"] == "unknown" and not first["alerts"]
    second = build_day(plan, docs, end, first)
    assert second["tasks"][0]["fulfillment"] == "interrupted" and len(second["alerts"]) == 1
    third = build_day(plan, docs, date(2026, 11, 8), second)
    assert not third["alerts"]
    assert any(rel == "FULFILLMENT_BASIS" for _, rel, _ in third["graph"]["edges"])


def test_reject_compound_assertion_when_secondary_source_cannot_support_original_span():
    p = Passage("law", "official journal", "d", "2026-04-15", 1, "The agreement will provisionally apply from May.")
    claim = Claim(
        text="Provisional application activated all annual quotas.",
        scope="trade agreement",
        topic="international",
        kind="observation",
        citation=p.id,
    )

    def judge(model, instruction, data):
        if model is Verdict:
            return Verdict(
                status="supported",
                quote=p.text,
                evidence_id=p.id,
                reason="On topic",
                direct=True,
                fulfillment="unknown",
            )
        assert model is SpanCheck and "evidence" not in data
        return SpanCheck(every_clause_supported=False, answers_named_scope=True, explanation="Quota effect missing.")

    result = audit(claim, {p.id: p}, date(2026, 5, 21), llm=judge, retries=0)
    assert result["status"] == "partial" and result["follow_up"]


def test_quantity_matching_preserves_sign_and_normalizes_german_grouping():
    from src.annual_reports.audit import quantities

    assert quantities("2025 acreage was 305,800 ha") == quantities("2025 auf 305.800 ha", german=True)
    assert quantities("-18.2%") != quantities("+18,2%", german=True)
