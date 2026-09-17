from people_memory.repository import _name_similarity


def test_typo_is_caught_above_the_read_floor():
    # The 2026-09-14 case: one letter wrong in a surname heard on a voice note.
    assert _name_similarity("Dominique Faurien", "Dominique Forien") >= 0.62


def test_reordered_names_match():
    assert _name_similarity("Forien Dominique", "Dominique Forien") >= 0.9


def test_unrelated_names_stay_below_the_floor():
    assert _name_similarity("Dominique Forien", "Katie LaFranchi") < 0.62
