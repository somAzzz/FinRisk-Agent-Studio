# README Redesign Specification

**Date**: 2026-03-27
**Task**: Redesign README.md for FinText-LLM project
**Status**: Implemented (commit `94cbaae docs: redesign README with layered progressive structure`), subsequently superseded — the README was rewritten again when the project merged with FinRisk-Agent-Studio (2026-06-25). Kept as the historical design rationale for the layered progressive structure.

## Overview

Redesign the project README to better serve all audiences (financial analysts, developers, researchers) with a layered progressive structure.

## Design Principles

1. **Layered Progressive**: From overview to deep-dive, readers can stop at any level
2. **Comprehensive but Concise**: Cover all features without bloat
3. **Exclude Tool Comparison System**: Recent work on `scripts/compare_tools/` not included in README
4. **Maintain Consistency**: Keep existing successful elements

## Structure

### 1. Project Overview (~2 lines)
- One-line description
- Core value proposition

### 2. Features Overview (5 core modules)
- Macro Risk Alert
- Management Sentiment Deviation
- Policy & Transition Risk
- Second-Order Supply Chain
- Browser Exploration

### 3. Quick Start (3 steps)
- `uv sync`
- `docker compose up -d`
- Optional: EDGAR data download

### 4. Core Features Detail
- Browser Exploration (expanded)
- Web Tools (web_search, web_fetch with time_range)
- EDGAR Analysis

### 5. Architecture
- Data flow diagram (text-based)

### 6. Project Structure
- Tree structure with key file annotations

### 7. Developer Guide
- Testing: `pytest`
- Linting: `ruff check`
- Dependencies: `uv sync`

## Exclusions
- Tool Comparison System (`scripts/compare_tools/`) excluded from README

## Implementation Notes
- Use existing README styling
- Keep code examples functional
- Add web_search/web_fetch tools section
- Expand Browser Exploration section
