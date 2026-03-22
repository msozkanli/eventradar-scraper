from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class RawEvent:
    source_id: str          # "biletzero"
    external_id: str        # kaynak sitedeki ID/slug
    title: str
    category: str           # "Konser", "Tiyatro", etc.
    start_date: Optional[str]   # ISO format
    end_date: Optional[str]
    venue_name: Optional[str]
    venue_city: Optional[str]
    price_min: Optional[int]
    price_max: Optional[int]
    image_url: Optional[str]
    ticket_url: str         # biletzero.com/... linki
    description: Optional[str]


class EventSource(ABC):
    @property
    @abstractmethod
    def source_id(self) -> str:
        pass

    @abstractmethod
    async def fetch_events(self, city: str = None) -> list[RawEvent]:
        pass
