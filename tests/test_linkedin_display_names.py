"""One person retyping their own headline — and two people who merely look alike.

A LinkedIn sync re-reads every connection's display name on every run, and members edit theirs:
a charter lands after a comma, an accent is dropped, a surname is cut to its initial. Each edit
turns a stored record into a "different name" and the sync asks a question nobody can answer more
reliably than the profile URL already has.

The two lists below encode the trade. VARIANTS must stop being asked about. NOT_VARIANTS must keep
being asked about — and the last pair is the one that matters most: on the installation this was
measured on, one record out of 635 carried another person's profile URL, and this branch was the
only thing reporting it. A rule that accepted the URL on its own would have silenced the only
witness and then written the wrong person's employer on top of that record.

Names here are invented, per this repo's convention.
"""

import os

import pytest

from people_memory.config import Settings
from people_memory.db import Database
from people_memory.repository import (
    GraphRepository,
    _display_name_key,
    _is_display_name_variant,
)

VARIANTS = [
    ("Aster Vale", "Aster Vale, CAIA"),  # a credential after a comma
    ("Aster Vale", "Aster Vale | CISSP, CISM"),  # a credential after a pipe
    ("Aster Vale", "Aster Vale — Cloud Security"),  # a tagline after a dash
    ("Aster .Vale", "Aster Vale"),  # a stray full stop inside the name
    ("Aster Valé", "Aster Vale"),  # an accent dropped
    ("Aster Vale", "ASTER VALE"),  # case
    ("Aster Vale 🛡 ⚖️", "Aster Vale 🛡⚖️"),  # a space between emoji
    ("Aster Vale", "Aster  Vale "),  # doubled and trailing space
    ("Aster Vale", "Aster V"),  # a surname cut to its initial
    ("Aster Vale", "Aster Val"),  # a surname cut short
]

NOT_VARIANTS = [
    ("Aster Vale", "Nova Lumen"),  # the measured case: a URL on the wrong record
    ("Aster Vale", "Aster Vane"),  # one letter apart, and two different people
    ("Aster Vale", "Aster Vale Junior"),  # an extra token is not a spelling
    ("Aster Vale", "Vale Aster"),  # reordered: which is the surname is not ours to decide
    ("Aster Vale", "Aster"),  # a token short, not a token abbreviated
    ("Aster Vale", "Asten Vale"),  # an abbreviation may only be the FINAL token
    ("Aster Vale", "Aster Wale"),  # a prefix relation that does not exist
]


@pytest.mark.parametrize(("stored", "incoming"), VARIANTS)
def test_one_person_retyping_their_name_is_recognised(stored: str, incoming: str) -> None:
    assert _is_display_name_variant(stored, incoming)
    # Symmetric: which side the graph happens to hold carries no meaning.
    assert _is_display_name_variant(incoming, stored)


@pytest.mark.parametrize(("stored", "incoming"), NOT_VARIANTS)
def test_two_different_people_are_still_two(stored: str, incoming: str) -> None:
    assert not _is_display_name_variant(stored, incoming)
    assert not _is_display_name_variant(incoming, stored)


def test_a_name_with_nothing_to_key_on_never_matches() -> None:
    # An empty key matching anything would make every punctuation-only name the same person as
    # every other, which is the worst failure this file exists to prevent.
    assert _display_name_key("   ") == ""
    assert _display_name_key("!!!") == ""
    assert not _is_display_name_variant("!!!", "???")
    assert not _is_display_name_variant("", "Aster Vale")


def _repo() -> GraphRepository:
    url = os.environ.get("PEOPLE_MEMORY_TEST_DATABASE_URL")
    if not url:
        pytest.skip("PEOPLE_MEMORY_TEST_DATABASE_URL is not set")
    return GraphRepository(
        Database(
            Settings(
                database_url=url,
                api_token=None,
                enable_raw_sql=True,
                default_source="test",
                cors_origins=(),
            )
        )
    )


@pytest.fixture
def repo() -> GraphRepository:
    repository = _repo()
    with repository.db.connection() as conn:
        conn.execute(
            "truncate deleted_records, interactions, facts, edges, affiliations, identifiers, "
            "org_aliases, orgs, people restart identity cascade"
        )
    return repository


PROFILE = "https://www.linkedin.com/in/aster-vale-1815"


def _stored_person(repo: GraphRepository, name: str, url: str | None = PROFILE) -> int:
    created = repo.remember_person(
        full_name=name, linkedin_url=url, confirmed_new=True, source="test"
    )
    assert created["status"] == "created", created
    return created["person"]["id"]


@pytest.mark.integration
def test_a_credential_added_to_a_headline_stops_asking(repo: GraphRepository) -> None:
    person_id = _stored_person(repo, "Aster Vale")
    result = repo.remember_person(
        full_name="Aster Vale, CAIA",
        linkedin_url=PROFILE,
        current_org="Analytical Engine Co",
        source="test",
    )
    assert result["status"] == "updated", result
    assert result["person"]["id"] == person_id
    # The stored name is left alone: the sync is not entitled to rename anybody, and the record
    # keeps whatever spelling a human chose for it.
    assert result["person"]["full_name"] == "Aster Vale"


@pytest.mark.integration
def test_a_profile_url_on_the_wrong_record_is_still_reported(repo: GraphRepository) -> None:
    # The measured failure, and the reason the URL alone is not enough: the record is named after
    # one person and carries another's profile URL. Nothing else in the graph reports this.
    _stored_person(repo, "Nova Lumen", url=PROFILE)
    result = repo.remember_person(
        full_name="Aster Vale",
        linkedin_url=PROFILE,
        current_org="Analytical Engine Co",
        source="test",
    )
    assert result["status"] == "needs_confirmation", result
    assert result["candidates"][0]["full_name"] == "Nova Lumen"


@pytest.mark.integration
def test_an_email_match_alone_never_settles_a_different_name(repo: GraphRepository) -> None:
    # No URL on the incoming record: the old question stands, exactly as before this change.
    repo.remember_person(
        full_name="Nova Lumen",
        email="shared@example.invalid",
        linkedin_url=None,
        confirmed_new=True,
        source="test",
    )
    result = repo.remember_person(
        full_name="Aster Vale", email="shared@example.invalid", source="test"
    )
    assert result["status"] == "needs_confirmation", result


@pytest.mark.integration
def test_a_url_the_graph_does_not_know_settles_nothing(repo: GraphRepository) -> None:
    # The sharpest case for the conjunction: the two names ARE variants, but the record was found
    # by its email and the incoming profile URL belongs to nobody here. Then the URL has identified
    # no one, it is only a string the sender supplied, and the question stands.
    repo.remember_person(
        full_name="Aster Vale",
        email="aster@example.invalid",
        linkedin_url=None,
        confirmed_new=True,
        source="test",
    )
    result = repo.remember_person(
        full_name="Aster Vale, CAIA",
        email="aster@example.invalid",
        linkedin_url="https://www.linkedin.com/in/someone-else-9999",
        source="test",
    )
    assert result["status"] == "needs_confirmation", result
