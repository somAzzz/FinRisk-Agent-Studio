"""Production-compatible clients backed by typed Pydantic AI Agents."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic_ai import Agent
from pydantic_ai.models import Model

from src.agents.extraction_agent import ExtractionResult, chunk_text
from src.ai.agents.structured import (
    build_filing_extraction_agent,
    build_generic_extraction_agent,
    build_node_profile_agent,
    build_relation_extraction_agent,
    build_requirement_decomposition_agent,
    build_supplier_proposal_agent,
)
from src.ai.deps import AgentDeps, AgentServices, AgentSubject
from src.ai.runtime_adapter import run_awaitable_sync
from src.config import Settings
from src.schemas.finrisk import ChunkValidation, ExtractedRisk, LLMCall
from src.schemas.llm_config import LLMRunConfig
from src.supply_chain.llm_extraction import SupplierRelationExtraction
from src.supply_chain.llm_models import (
    NodeProfileBatch,
    RequirementDecomposition,
    SupplierProposalBatch,
)

SupplyChainOutput = TypeVar(
    "SupplyChainOutput",
    RequirementDecomposition,
    SupplierProposalBatch,
    NodeProfileBatch,
)


class PydanticAIFilingExtractionClient:
    """Expose the existing chunked-client protocol using typed Agent output."""

    provider = "pydantic_ai"

    def __init__(
        self,
        *,
        model: Model,
        settings: Settings,
        services: AgentServices | None = None,
        llm_call_sink: Callable[[LLMCall], None] | None = None,
    ) -> None:
        self.model = model
        self.model_name = model.model_name
        self.settings = settings
        self.services = services or AgentServices()
        self.llm_call_sink = llm_call_sink
        self.agent = build_filing_extraction_agent(model)

    def extract_risks_chunked(
        self,
        text: str,
        *,
        company_name: str,
        year: int,
        source_id: str,
        chunk_size: int,
        overlap: int,
        step_name: str,
    ) -> tuple[list[ExtractedRisk], list[ChunkValidation], list[LLMCall]]:
        risks: list[ExtractedRisk] = []
        validations: list[ChunkValidation] = []
        calls: list[LLMCall] = []
        for index, chunk in enumerate(
            chunk_text(
                text,
                source_id=source_id,
                source_type="filing",
                section="section_1a",
                chunk_size=chunk_size,
                overlap=overlap,
            )
        ):
            chunk_id = f"{source_id}:chunk-{index:04d}"
            run_id = f"filing-{uuid.uuid4().hex[:12]}"
            deps = AgentDeps(
                run_id=run_id,
                conversation_id=f"filing:{source_id}",
                settings=self.settings,
                subject=AgentSubject(
                    company_name=company_name,
                    metadata={"year": year, "source_id": source_id},
                ),
                services=self.services,
            )
            prompt = (
                f"Company: {company_name}\nYear: {year}\n"
                f"Source: {source_id}\nChunk: {chunk_id}\n\n{chunk.text}"
            )
            started_at = datetime.now(UTC)
            started = time.perf_counter()
            result = run_awaitable_sync(
                self.agent.run(prompt, deps=deps, run_id=run_id)
            )
            completed_at = datetime.now(UTC)
            output = result.output
            risks.extend(output.risks)
            validation = ChunkValidation(
                chunk_id=chunk_id,
                pydantic_model="FilingRiskExtractionOutput",
                ok=True,
                errors=list(output.warnings),
                validated_count=len(output.risks),
                dropped_count=0,
                fallback_used="llm",
                section_name=chunk.section,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                validated_at=completed_at,
            )
            validations.append(validation)
            usage = result.usage
            messages = json.loads(result.all_messages_json())
            call = LLMCall(
                call_id=f"pai-{uuid.uuid4().hex[:12]}",
                step_name=step_name,
                chunk_id=chunk_id,
                provider=self.provider,
                model=self.model_name,
                messages=messages,
                prompt_text=prompt,
                response_text=result.output.model_dump_json(),
                response_structured=result.output.model_dump(mode="json"),
                prompt_tokens=usage.input_tokens,
                completion_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens,
                latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
                started_at=started_at,
                completed_at=completed_at,
            )
            calls.append(call)
            if self.llm_call_sink is not None:
                self.llm_call_sink(call)
            recorder = self.services.message_recorder
            if recorder is not None:
                run_awaitable_sync(
                    recorder.record_result(
                        run_id=run_id,
                        conversation_id=deps.conversation_id or run_id,
                        agent_name=self.agent.name or "filing_risk_extractor",
                        result=result,
                    )
                )
        return risks, validations, calls

    def extract_risks(
        self, text: str, *, company_name: str, year: int
    ) -> dict[str, Any]:
        risks, _validations, _calls = self.extract_risks_chunked(
            text,
            company_name=company_name,
            year=year,
            source_id="filing:single-shot",
            chunk_size=max(1, len(text)),
            overlap=0,
            step_name="filing_risk_extractor",
        )
        return {"risks": [risk.model_dump(mode="json") for risk in risks]}


class PydanticAISupplierRelationClient:
    """Typed supply-chain relation extractor used in primary mode."""

    provider = "pydantic_ai"

    def __init__(
        self,
        *,
        model: Model,
        settings: Settings,
        services: AgentServices | None = None,
    ) -> None:
        self.model = model
        self.model_name = model.model_name
        self.settings = settings
        self.services = services or AgentServices()
        self.agent = build_relation_extraction_agent(model)

    def extract_supplier_relations(
        self,
        *,
        prompt: str,
        company_name: str | None,
        product_name: str,
        max_suppliers: int,
    ) -> tuple[list[SupplierRelationExtraction], str]:
        run_id = f"relation-{uuid.uuid4().hex[:12]}"
        deps = AgentDeps(
            run_id=run_id,
            conversation_id=f"supply-chain:{company_name or product_name}",
            settings=self.settings,
            subject=AgentSubject(
                company_name=company_name,
                product_name=product_name,
            ),
            services=self.services,
        )
        result = run_awaitable_sync(
            self.agent.run(prompt, deps=deps, run_id=run_id)
        )
        output = result.output
        recorder = self.services.message_recorder
        if recorder is not None:
            run_awaitable_sync(
                recorder.record_result(
                    run_id=run_id,
                    conversation_id=deps.conversation_id or run_id,
                    agent_name=self.agent.name or "relation_extractor",
                    result=result,
                )
            )
        return output.relations[:max_suppliers], output.model_dump_json()


class PydanticAISupplyChainClient(PydanticAISupplierRelationClient):
    """Typed boundary for every model-backed supply-chain analysis step."""

    def __init__(
        self,
        *,
        model: Model,
        settings: Settings,
        services: AgentServices | None = None,
    ) -> None:
        super().__init__(model=model, settings=settings, services=services)
        self.requirement_agent = build_requirement_decomposition_agent(model)
        self.supplier_proposal_agent = build_supplier_proposal_agent(model)
        self.node_profile_agent = build_node_profile_agent(model)

    def decompose_requirements(self, prompt: str) -> RequirementDecomposition:
        return self._run_supply_chain_agent(
            self.requirement_agent,
            prompt,
            run_prefix="requirements",
        )

    def propose_suppliers(self, prompt: str) -> SupplierProposalBatch:
        return self._run_supply_chain_agent(
            self.supplier_proposal_agent,
            prompt,
            run_prefix="suppliers",
        )

    def profile_nodes(self, prompt: str) -> NodeProfileBatch:
        return self._run_supply_chain_agent(
            self.node_profile_agent,
            prompt,
            run_prefix="profiles",
        )

    def _run_supply_chain_agent(
        self,
        agent: Agent[AgentDeps, SupplyChainOutput],
        prompt: str,
        *,
        run_prefix: str,
    ) -> SupplyChainOutput:
        run_id = f"supply-{run_prefix}-{uuid.uuid4().hex[:12]}"
        deps = AgentDeps(
            run_id=run_id,
            conversation_id=run_id,
            settings=self.settings,
            services=self.services,
        )
        result = run_awaitable_sync(
            agent.run(prompt, deps=deps, run_id=run_id)
        )
        recorder = self.services.message_recorder
        if recorder is not None:
            run_awaitable_sync(
                recorder.record_result(
                    run_id=run_id,
                    conversation_id=run_id,
                    agent_name=agent.name or f"supply_chain_{run_prefix}",
                    result=result,
                )
            )
        return result.output


class PydanticAIGenericExtractionClient:
    """Typed extraction boundary for filing, transcript, and web agents."""

    provider = "pydantic_ai"

    def __init__(
        self,
        *,
        model: Model,
        settings: Settings,
        services: AgentServices | None = None,
    ) -> None:
        self.model = model
        self.model_name = model.model_name
        self.settings = settings
        self.services = services or AgentServices()
        self.agent = build_generic_extraction_agent(model)

    def extract(self, prompt: str) -> ExtractionResult:
        """Return one validated ``ExtractionResult`` from source text."""
        run_id = f"extraction-{uuid.uuid4().hex[:12]}"
        deps = AgentDeps(
            run_id=run_id,
            conversation_id=run_id,
            settings=self.settings,
            services=self.services,
        )
        result = run_awaitable_sync(
            self.agent.run(prompt, deps=deps, run_id=run_id)
        )
        recorder = self.services.message_recorder
        if recorder is not None:
            run_awaitable_sync(
                recorder.record_result(
                    run_id=run_id,
                    conversation_id=run_id,
                    agent_name=self.agent.name or "generic_structured_extractor",
                    result=result,
                )
            )
        return result.output


def build_generic_extraction_client(
    llm_config: LLMRunConfig | None = None,
) -> PydanticAIGenericExtractionClient:
    """Build the typed generic extractor through the central model factory."""
    from src.ai.model_factory import build_agent_model, resolve_agent_model_config
    from src.ai.store_factory import get_agent_run_recorder
    from src.config import get_settings

    settings = get_settings()
    return PydanticAIGenericExtractionClient(
        model=build_agent_model(
            resolve_agent_model_config(llm_config, settings=settings)
        ),
        settings=settings,
        services=AgentServices(message_recorder=get_agent_run_recorder()),
    )


__all__ = [
    "PydanticAIFilingExtractionClient",
    "PydanticAIGenericExtractionClient",
    "PydanticAISupplierRelationClient",
    "PydanticAISupplyChainClient",
    "build_generic_extraction_client",
]
