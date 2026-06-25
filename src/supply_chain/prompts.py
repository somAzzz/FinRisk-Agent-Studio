"""v18 search intent templates.

The search provider family (Brave, DuckDuckGo, etc.) takes a
``SearchIntent`` and a query string. The v18 explorer adds six
intents for product supply chain discovery. The map below
maps each intent to a query template; the test
``tests/supply_chain/test_supplier_discovery`` asserts the
templates render correctly.
"""

from __future__ import annotations

INTENT_QUERY_TEMPLATES: dict[str, str] = {
    "product_supply_chain": (
        "{q} product supply chain suppliers upstream components"
    ),
    "supplier_discovery": (
        "{q} suppliers companies official partnership evidence"
    ),
    "component_supplier": (
        "{q} major suppliers manufacturers market share"
    ),
    "cloud_dependency": (
        "{q} cloud provider datacenter infrastructure supplier"
    ),
    "datacenter_power": (
        "{q} datacenter power electricity supplier energy contract"
    ),
    "semiconductor_supply_chain": (
        "{q} semiconductor upstream foundry HBM lithography suppliers"
    ),
}


def render_query(intent: str, q: str) -> str:
    """Return the rendered query for ``intent`` and ``q``.

    Unknown intents fall back to the raw query so callers can
    experiment with custom intents without raising.
    """
    template = INTENT_QUERY_TEMPLATES.get(intent)
    if template is None:
        return q
    return template.format(q=q)


__all__ = ["INTENT_QUERY_TEMPLATES", "render_query"]
