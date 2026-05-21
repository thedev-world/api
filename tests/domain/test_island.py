from __future__ import annotations

from app.domain.island import IslandChoice


def test_island_choice_has_ten_values() -> None:
    assert len(IslandChoice) == 10


def test_all_islands_have_a_non_empty_label() -> None:
    for island in IslandChoice:
        assert island.label
        assert island.label.endswith("Island")


def test_each_island_label_is_unique() -> None:
    labels = [island.label for island in IslandChoice]
    assert len(labels) == len(set(labels))


def test_island_values_are_lowercase_strings() -> None:
    for island in IslandChoice:
        assert island.value == island.value.lower()


def test_specific_labels() -> None:
    assert IslandChoice.FRONTEND.label == "Frontend Island"
    assert IslandChoice.BACKEND.label == "Backend Island"
    assert IslandChoice.AI.label == "AI Island"
    assert IslandChoice.OPEN_SOURCE.label == "Open Source Island"
    assert IslandChoice.INDIE_HACKER.label == "Indie Hacker Island"


def test_island_is_valid_str() -> None:
    assert IslandChoice("frontend") is IslandChoice.FRONTEND
    assert IslandChoice("vibe_coding") is IslandChoice.VIBE_CODING
