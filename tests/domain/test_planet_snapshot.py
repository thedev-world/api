from __future__ import annotations

from datetime import datetime

import pytest
from app.domain.planet_snapshot import PlanetEntry, generate_planet_payload
from app.domain.scoring import get_cell_count


def test_empty_entries_returns_empty_islands_dict() -> None:
    payload = generate_planet_payload([])

    assert payload["islands"] == {}


def test_updated_at_is_valid_utc_iso_string() -> None:
    payload = generate_planet_payload([])

    updated_at = datetime.fromisoformat(payload["updated_at"])  # type: ignore[arg-type]
    assert updated_at.tzinfo is not None
    assert updated_at.tzinfo.utcoffset(updated_at).total_seconds() == 0  # type: ignore[union-attr]


def test_single_entry_is_grouped_under_its_island() -> None:
    entry = PlanetEntry(login="torvalds", island_id="backend", xp_brut=50_000)
    payload = generate_planet_payload([entry])

    islands = payload["islands"]
    assert list(islands.keys()) == ["backend"]  # type: ignore[union-attr]
    login, cell_count = islands["backend"][0]  # type: ignore[index]
    assert login == "torvalds"
    assert cell_count == get_cell_count(50_000)


def test_cell_count_matches_scoring_formula() -> None:
    cases = [
        PlanetEntry(login="a", island_id="frontend", xp_brut=0),
        PlanetEntry(login="b", island_id="ai", xp_brut=500),
        PlanetEntry(login="c", island_id="backend", xp_brut=22_000),
        PlanetEntry(login="d", island_id="backend", xp_brut=115_000),
        PlanetEntry(login="e", island_id="mobile", xp_brut=800_000),
    ]
    payload = generate_planet_payload(cases)
    islands = payload["islands"]  # type: ignore[index]

    assert islands["frontend"][0][1] == get_cell_count(0)
    assert islands["ai"][0][1] == get_cell_count(500)
    assert islands["backend"][0][1] == get_cell_count(22_000)
    assert islands["backend"][1][1] == get_cell_count(115_000)
    assert islands["mobile"][0][1] == get_cell_count(800_000)


def test_multiple_entries_same_island_preserve_order() -> None:
    entries = [
        PlanetEntry(login="alpha", island_id="frontend", xp_brut=1_000),
        PlanetEntry(login="beta", island_id="frontend", xp_brut=2_000),
        PlanetEntry(login="gamma", island_id="frontend", xp_brut=3_000),
    ]
    payload = generate_planet_payload(entries)

    logins = [row[0] for row in payload["islands"]["frontend"]]  # type: ignore[index]
    assert logins == ["alpha", "beta", "gamma"]


def test_same_island_preserves_signup_order() -> None:
    entries = [
        PlanetEntry(login="zebra", island_id="frontend", xp_brut=1_000),
        PlanetEntry(login="alpha", island_id="frontend", xp_brut=2_000),
    ]
    payload = generate_planet_payload(entries)

    logins = [row[0] for row in payload["islands"]["frontend"]]  # type: ignore[index]
    assert logins == ["zebra", "alpha"]


def test_entries_grouped_by_island() -> None:
    entries = [
        PlanetEntry(login="alice", island_id="frontend", xp_brut=1_000),
        PlanetEntry(login="bob", island_id="backend", xp_brut=2_000),
        PlanetEntry(login="carol", island_id="frontend", xp_brut=3_000),
    ]
    payload = generate_planet_payload(entries)
    islands = payload["islands"]  # type: ignore[index]

    assert set(islands.keys()) == {"frontend", "backend"}
    assert len(islands["frontend"]) == 2
    assert len(islands["backend"]) == 1
    assert islands["frontend"][0][0] == "alice"
    assert islands["frontend"][1][0] == "carol"


@pytest.mark.parametrize("xp_brut", [0, 1, 199, 200, 1_140, 6_300, 115_000, 398_000])
def test_cell_count_never_zero(xp_brut: int) -> None:
    entry = PlanetEntry(login="x", island_id="frontend", xp_brut=xp_brut)
    payload = generate_planet_payload([entry])

    assert payload["islands"]["frontend"][0][1] >= 1  # type: ignore[index]
