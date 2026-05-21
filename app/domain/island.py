from __future__ import annotations

import enum


class IslandChoice(enum.StrEnum):
    FRONTEND = "frontend"
    BACKEND = "backend"
    FULLSTACK = "fullstack"
    INFRA = "infra"
    VIBE_CODING = "vibe_coding"
    AI = "ai"
    OPEN_SOURCE = "open_source"
    INDIE_HACKER = "indie_hacker"
    MOBILE = "mobile"
    DATA = "data"

    @property
    def label(self) -> str:
        labels = {
            "frontend": "Frontend Island",
            "backend": "Backend Island",
            "fullstack": "Fullstack Island",
            "infra": "Infra Island",
            "vibe_coding": "Vibe Coding Island",
            "ai": "AI Island",
            "open_source": "Open Source Island",
            "indie_hacker": "Indie Hacker Island",
            "mobile": "Mobile Island",
            "data": "Data Island",
        }
        return labels[self.value]
