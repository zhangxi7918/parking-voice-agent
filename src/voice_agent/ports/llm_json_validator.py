from __future__ import annotations

from typing import Protocol

from voice_agent.domain.visitor import VisitorIntake


class LlmJsonValidator(Protocol):
    async def normalize(self, raw_text: str, current: VisitorIntake) -> VisitorIntake:
        """Normalize free-form dialogue into a visitor intake object."""

