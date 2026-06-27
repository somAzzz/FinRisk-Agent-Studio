"""Tests for sensitive-value redaction in LLM audit rows."""

from __future__ import annotations

from datetime import UTC, datetime

from src.schemas.finrisk import LLMCall


def test_llm_call_redacts_sensitive_text_fields() -> None:
    now = datetime.now(tz=UTC)
    call = LLMCall(
        call_id="llm-test",
        step_name="filing_risk_extractor",
        provider="test",
        model="model",
        messages=[
            {
                "role": "user",
                "content": "Contact jane@example.com with key sk-abcdefghijklmnopqrstuvwxyz123456",
            }
        ],
        prompt_text="Phone 555-123-4567 and token Bearer abcdefghijklmnopqrstuvwxyz",
        response_text="Card 1234 5678 9012 3456",
        response_structured={
            "nested": ["SSN 123-45-6789", "safe text"],
        },
        latency_ms=1,
        started_at=now,
        completed_at=now,
    )

    dumped = call.model_dump()
    rendered = str(dumped)
    assert "jane@example.com" not in rendered
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in rendered
    assert "555-123-4567" not in rendered
    assert "1234 5678 9012 3456" not in rendered
    assert "123-45-6789" not in rendered
    assert "[EMAIL]" in rendered
    assert "[API_KEY]" in rendered
    assert "[PHONE]" in rendered
    assert "[CARD]" in rendered
    assert "[SSN]" in rendered
