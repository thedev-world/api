from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.domain.scoring import get_cell_count


@dataclass(frozen=True, slots=True)
class PlanetEntry:
    login: str
    island_id: str
    xp_brut: int


def generate_planet_payload(entries: list[PlanetEntry]) -> dict[str, object]:
    """Build the planet-data.json payload from a list of onboarded developers.

    Format is kept compact to minimise the size of the static file:
    each developer is encoded as a 3-element list [login, island_id, cell_count].
    """
    return {
        "updated_at": datetime.now(UTC).isoformat(),
        "developers": [
            [entry.login, entry.island_id, get_cell_count(entry.xp_brut)] for entry in entries
        ],
    }
