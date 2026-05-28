from __future__ import annotations

from datetime import datetime

import pytest
from app.domain.planet_snapshot import PlanetEntry, generate_planet_payload
from app.domain.scoring import get_cell_count


def test_empty_entries_returns_empty_developers_list() -> None:
    payload = generate_planet_payload([])

    assert payload["developers"] == []


def test_updated_at_is_valid_utc_iso_string() -> None:
    payload = generate_planet_payload([])

    updated_at = datetime.fromisoformat(payload["updated_at"])  # type: ignore[arg-type]
    assert updated_at.tzinfo is not None
    assert updated_at.tzinfo.utcoffset(updated_at).total_seconds() == 0  # type: ignore[union-attr]


def test_single_entry_produces_correct_tuple() -> None:
    entry = PlanetEntry(login="torvalds", island_id="backend", xp_brut=50_000)
    payload = generate_planet_payload([entry])

    devs = payload["developers"]
    assert len(devs) == 1
    login, island_id, cell_count = devs[0]
    assert login == "torvalds"
    assert island_id == "backend"
    assert cell_count == get_cell_count(50_000)


def test_cell_count_matches_scoring_formula() -> None:
    cases = [
        PlanetEntry(login="a", island_id="frontend", xp_brut=0),
        PlanetEntry(login="b", island_id="ai", xp_brut=500),
        PlanetEntry(login="c", island_id="devops", xp_brut=22_000),
        PlanetEntry(login="d", island_id="backend", xp_brut=115_000),
        PlanetEntry(login="e", island_id="mobile", xp_brut=800_000),
    ]
    payload = generate_planet_payload(cases)

    for entry, dev_row in zip(cases, payload["developers"], strict=True):
        assert dev_row[2] == get_cell_count(entry.xp_brut)


def test_multiple_entries_preserve_order() -> None:
    entries = [
        PlanetEntry(login="alpha", island_id="frontend", xp_brut=1_000),
        PlanetEntry(login="beta", island_id="backend", xp_brut=2_000),
        PlanetEntry(login="gamma", island_id="ai", xp_brut=3_000),
    ]
    payload = generate_planet_payload(entries)

    logins = [row[0] for row in payload["developers"]]
    assert logins == ["alpha", "beta", "gamma"]


@pytest.mark.parametrize("xp_brut", [0, 1, 199, 200, 1_140, 6_300, 115_000, 398_000])
def test_cell_count_never_zero(xp_brut: int) -> None:
    entry = PlanetEntry(login="x", island_id="frontend", xp_brut=xp_brut)
    payload = generate_planet_payload([entry])

    assert payload["developers"][0][2] >= 1
