from __future__ import annotations

from typing import Protocol

from src.models import ParsedOffer


class OfferExtractor(Protocol):
    def extract(self, snapshot_text: str) -> list[ParsedOffer]:
        ...
