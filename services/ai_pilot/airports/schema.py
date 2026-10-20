"""Small JSON-friendly schema for sourced airport data."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourcedValue:
    """A value paired with where it came from and how it was interpreted."""

    value: Any
    source: str | None
    confidence: str = "high"
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value,
                "provenance": {"source": self.source,
                               "confidence": self.confidence,
                               **({"detail": self.detail} if self.detail else {})}}


@dataclass
class RunwayEndRecord:
    icao: str
    runway_end: str
    runway_name: str
    fields: dict[str, SourcedValue] = field(default_factory=dict)
    source_values: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    disagreements: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "icao": self.icao,
            "runway_end": self.runway_end,
            "runway_name": self.runway_name,
            "fields": {name: value.to_dict() for name, value in self.fields.items()},
            "source_values": self.source_values,
            "disagreements": self.disagreements,
            "missing": list(self.missing),
        }


@dataclass
class AirportRecord:
    icao: str
    name: str
    fields: dict[str, SourcedValue]
    runway_ends: list[RunwayEndRecord]
    validation_report: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "icao": self.icao,
            "name": self.name,
            "fields": {name: value.to_dict() for name, value in self.fields.items()},
            "runway_ends": [end.to_dict() for end in self.runway_ends],
            "validation_report": self.validation_report,
        }
