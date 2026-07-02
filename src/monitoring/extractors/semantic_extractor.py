from __future__ import annotations

import json
from typing import Any, Callable

from src.models import ParsedOffer


SemanticExtractorProvider = Callable[[str], str | dict[str, Any] | list[dict[str, Any]]]


class SemanticOfferExtractor:
    """
    Schema-shaped semantic extraction hook.

    A production provider can call an LLM with the MCP accessibility snapshot and
    return JSON matching ParsedOffer fields. The default provider is disabled so
    local dry-runs never make network calls.
    """

    def __init__(self, provider: SemanticExtractorProvider | None = None) -> None:
        self.provider = provider

    def extract(self, snapshot_text: str) -> list[ParsedOffer]:
        if self.provider is None:
            return []

        raw = self.provider(snapshot_text)
        payload = json.loads(raw) if isinstance(raw, str) else raw
        items = payload.get("offers", []) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            return []

        offers: list[ParsedOffer] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            parsed = self._coerce_offer(item, snapshot_text)
            if parsed is not None:
                offers.append(parsed)
        return offers

    def _coerce_offer(self, item: dict[str, Any], snapshot_text: str) -> ParsedOffer | None:
        try:
            title = str(item["title"]).strip()
            section = str(item.get("section") or "Unknown").strip()
            quantity = int(item.get("quantity") or 1)
            total_usd = float(item["total_usd"])
        except (KeyError, TypeError, ValueError):
            return None

        if not title or quantity < 1 or total_usd <= 0:
            return None

        unit_price = item.get("unit_price_usd")
        available_seats = item.get("available_seats")
        confidence = float(item.get("confidence") or 0.7)
        signals = item.get("signals") or ["semantic_extraction"]

        return ParsedOffer(
            title=title,
            section=section,
            quantity=quantity,
            total_usd=total_usd,
            unit_price_usd=float(unit_price) if unit_price is not None else None,
            available_seats=int(available_seats) if available_seats is not None else None,
            confidence=max(0.0, min(confidence, 1.0)),
            signals=[str(signal) for signal in signals],
            source_text=snapshot_text[:1000],
        )
