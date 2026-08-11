from people_memory.repository import _name_similarity


def test_name_similarity_catches_typo_and_reordered_name() -> None:
    assert _name_similarity("Aster Vale", "Aster Vail") >= 0.78
    assert _name_similarity("Aster Vale", "Vale Aster") == 1.0


def test_name_similarity_rejects_unrelated_people() -> None:
    assert _name_similarity("Aster Vale", "Nova Lumen") < 0.78
