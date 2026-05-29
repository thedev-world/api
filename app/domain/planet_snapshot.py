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

    Format is kept compact to minimise the size of the static file.
    Developers are grouped by island.

    Format: {"updated_at": ISO, "islands": {"frontend": [["login", cell_count], ...], ...}}
    """
    islands: dict[str, list[list[object]]] = {}
    for entry in entries:
        islands.setdefault(entry.island_id, []).append([entry.login, get_cell_count(entry.xp_brut)])

    return {
        "updated_at": datetime.now(UTC).isoformat(),
        "islands": islands,
    }
