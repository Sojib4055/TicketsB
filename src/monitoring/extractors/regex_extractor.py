from __future__ import annotations

from src.models import ParsedOffer
from src.monitoring.availability_parser import parse_offer_texts


class RegexOfferExtractor:
    def extract(self, snapshot_text: str) -> list[ParsedOffer]:
        return parse_offer_texts(snapshot_text)
