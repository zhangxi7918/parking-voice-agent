from __future__ import annotations

from dataclasses import asdict, dataclass, field


REQUIRED_FIELDS = (
    "visitor_name",
    "phone",
    "plate_number",
    "visit_purpose",
    "host_name",
)


@dataclass(slots=True)
class VisitorIntake:
    visitor_name: str | None = None
    phone: str | None = None
    plate_number: str | None = None
    company: str | None = None
    visit_purpose: str | None = None
    host_name: str | None = None
    arrival_time: str | None = None
    confidence: dict[str, float] = field(default_factory=dict)

    def missing_required_fields(self) -> list[str]:
        return [field_name for field_name in REQUIRED_FIELDS if not getattr(self, field_name)]

    def is_complete(self) -> bool:
        return not self.missing_required_fields()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "VisitorIntake":
        return cls(
            visitor_name=data.get("visitor_name"),
            phone=data.get("phone"),
            plate_number=data.get("plate_number"),
            company=data.get("company"),
            visit_purpose=data.get("visit_purpose"),
            host_name=data.get("host_name"),
            arrival_time=data.get("arrival_time"),
            confidence=dict(data.get("confidence") or {}),
        )

