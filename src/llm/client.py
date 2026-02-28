"""LLM client for risk extraction from EDGAR filings."""

import json
import os
import re
from typing import Any

from openai import OpenAI

DEFAULT_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
DEFAULT_MODEL = os.environ.get("VLLM_MODEL", "Qwen/Qwen3.5-35B-A3B")
DEFAULT_TEMPERATURE = 0.1
DEFAULT_MAX_TOKENS = 2000
MAX_INPUT_TOKENS = 1500


class RiskExtractorError(Exception):
    """Base exception for risk extraction errors."""

    pass


class EdgarLLMClient:
    """Client for extracting risks from EDGAR filings using vLLM."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ):
        """Initialize the LLM client.

        Args:
            base_url: vLLM server URL (default: from VLLM_BASE_URL env or localhost)
            api_key: API key (default: from VLLM_API_KEY env or "dummy")
            model: Model name (default: from VLLM_MODEL env or Qwen3.5-35B-A3B)
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
        """
        self.client = OpenAI(
            base_url=base_url or DEFAULT_BASE_URL,
            api_key=(
                api_key if api_key is not None
                else os.environ.get("VLLM_API_KEY", "dummy")
            ),
        )
        self.model = model or DEFAULT_MODEL
        self.temperature = temperature
        self.max_tokens = max_tokens

    def extract_risks(
        self,
        section_1a: str,
        company_name: str = "Unknown",
        year: int = 2020,
    ) *********REMOVED********* dict[str, Any]:
        """Extract macro risks from Item 1A (Risk Factors).

        Args:
            section_1a: The risk factors text from 10-K filing
            company_name: Company name for context
            year: Filing year

        Returns:
            Dictionary with extracted risks and severity scores

        Raises:
            ValueError: If section_1a is empty or None
        """
        if not section_1a or not section_1a.strip():
            raise ValueError("section_1a cannot be empty or None")

        prompt = self._build_prompt(section_1a, company_name)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        content = response.choices[0].message.content

        return self._parse_response(content, company_name, year)

    def _build_prompt(self, section_1a: str, company_name: str) *********REMOVED********* str:
        """Build the prompt for risk extraction."""
        truncated_text = section_1a[:MAX_INPUT_TOKENS]
        return f"""<|im_start|>system
Output only valid JSON in a code block. No thinking.
<|im_end|>
<|im_start|>user
Extract risks from 10-K Item 1A.

Company: {company_name}
Text: {truncated_text}
<|im_end|>"""

    def _parse_response(
        self,
        content: str,
        company_name: str,
        year: int,
    ) *********REMOVED********* dict[str, Any]:
        """Parse the LLM response to extract risks."""
        # Try to find JSON in markdown code blocks first
        json_in_markdown = re.findall(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content)
        for json_str in json_in_markdown:
            try:
                result = json.loads(json_str)
                if "risks" in result or "risk" in result:
                    return self._normalize_result(result, company_name, year)
            except json.JSONDecodeError:
                continue

        # Try to parse as JSON directly
        try:
            result = json.loads(content)
            return self._normalize_result(result, company_name, year)
        except json.JSONDecodeError:
            pass

        # Try to find any JSON-like structure in the response
        all_json_candidates = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", content)
        for candidate in reversed(all_json_candidates):
            try:
                result = json.loads(candidate)
                if "risks" in result or "risk" in result:
                    return self._normalize_result(result, company_name, year)
            except json.JSONDecodeError:
                continue

        return {
            "company": company_name,
            "year": year,
            "risks": [],
            "avg_severity": 0,
            "raw_response": content[:500],
        }

    def _normalize_result(
        self,
        result: dict[str, Any],
        company_name: str,
        year: int,
    ) *********REMOVED********* dict[str, Any]:
        """Normalize the result to a consistent format."""
        # Normalize field names
        if "risk" in result and "risks" not in result:
            result["risks"] = result.pop("risk")

        # Normalize risk structure
        if "risks" in result:
            normalized_risks = []
            for risk in result["risks"]:
                if isinstance(risk, str):
                    normalized_risks.append({
                        "risk_factor": risk,
                        "severity": 3,
                        "quote": "",
                    })
                elif isinstance(risk, dict):
                    rf = risk.get("risk_factor") or risk.get("description")
                    rf = rf or risk.get("risk", "Unknown")
                    sev = risk.get("severity", risk.get("risk_level", 3))
                    q = risk.get("quote", risk.get("text", ""))
                    normalized_risks.append({
                        "risk_factor": rf,
                        "severity": sev,
                        "quote": q,
                    })
            result["risks"] = normalized_risks

        # Set defaults
        result["company"] = company_name
        result["year"] = year

        # Calculate avg_severity if not present
        if "avg_severity" not in result and result.get("risks"):
            severities = [
                r.get("severity", 3) for r in result["risks"] if isinstance(r, dict)
            ]
            if severities:
                result["avg_severity"] = round(sum(severities) / len(severities), 2)

        return result
