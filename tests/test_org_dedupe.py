"""One organisation, however it was spelled — and two organisations when they really are two.

The two parametrised lists below encode the trade this feature makes. "Armée de terre" and
"Armée de Terre" must become one row; "BNP Paribas" and "BNP Paribas CIB" must stay two. Any
change to the normalisation that keeps the first and breaks the second has made the graph worse,
not better, and this file is where that shows.
"""

import os

import pytest

from people_memory.config import Settings
from people_memory.db import Database
from people_memory.repository import GraphRepository, _normalize_org_name

SAME = [
    ("Armée de terre", "Armée de Terre"),  # case
    ("ITrust", "ITrust SA"),  # trailing legal suffix
    ("Freelancer", "Freelance"),  # the one hard-coded synonym
    ("Ecole 2600", "École 2600"),  # accent
    ("Green IT Solutions", "green it solutions "),  # case and trailing space
    ("Publicis Sapient", "Publicis  Sapient"),  # doubled space
    ("Saint-Gobain", "Saint Gobain"),  # punctuation
]

DIFFERENT = [
    ("BNP Paribas", "BNP Paribas CIB"),
    ("BNP Paribas", "BNP Paribas Factoring"),
    ("KNDS France", "KPMG France"),
    ("Groupe TF1", "Groupe SII"),
    ("CS GROUP", "NAVAL GROUP"),
    ("Ecole 2600", "2600"),  # a real pair, and unreachable by rule: `org_aliases` handles it
    ("Groupe TF1", "TF1"),  # "Groupe" is never stripped: it can change which entity is meant
    ("SA", "SAS"),  # a suffix is never stripped when it is the whole name
]


@pytest.mark.parametrize(("left", "right"), SAME)
def test_spellings_of_one_organisation_share_a_key(left: str, right: str) -> None:
    assert _normalize_org_name(left) == _normalize_org_name(right)


@pytest.mark.parametrize(("left", "right"), DIFFERENT)
def test_different_organisations_keep_different_keys(left: str, right: str) -> None:
    assert _normalize_org_name(left) != _normalize_org_name(right)


def test_a_name_with_nothing_to_key_on_yields_no_key() -> None:
    # An empty key must never match: it would make every punctuation-only name the same
    # organisation as every other.
    assert _normalize_org_name("   ") == ""
    assert _normalize_org_name("!!!") == ""


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


@pytest.mark.integration
def test_the_sql_rule_and_the_python_rule_agree(repo: GraphRepository) -> None:
    # Two implementations of one rule is two chances to drift. The importer reads `org_norm()`
    # through an index and the trigger writes through it, so a disagreement is a duplicate.
    samples = [name for pair in SAME + DIFFERENT for name in pair]
    with repo.db.connection() as conn:
        for name in samples:
            in_sql = conn.execute("select org_norm(%s) as key", (name,)).fetchone()["key"]
            assert in_sql == _normalize_org_name(name), name


@pytest.mark.integration
def test_a_case_variant_lands_on_the_organisation_that_already_exists(
    repo: GraphRepository,
) -> None:
    first = repo.remember_person(
        full_name="Ada Lovelace",
        current_org="Armée de Terre",
        confirmed_new=True,
        source="test",
    )
    second = repo.remember_person(
        full_name="Grace Hopper",
        current_org="armée de terre",
        confirmed_new=True,
        source="test",
    )
    assert first["status"] == "created"
    assert second["status"] == "created"

    with repo.db.connection() as conn:
        names = [row["name"] for row in conn.execute("select name from orgs").fetchall()]
        assert names == ["Armée de Terre"]
        # The person carries the surviving spelling too: `current_org` is what the dashboard
        # groups by, so leaving the variant there leaves the duplicate visible.
        stored = conn.execute(
            "select current_org from people where full_name = 'Grace Hopper'"
        ).fetchone()
        assert stored["current_org"] == "Armée de Terre"


@pytest.mark.integration
def test_a_subsidiary_is_not_swallowed_by_its_parent(repo: GraphRepository) -> None:
    repo.remember_person(
        full_name="Ada Lovelace", current_org="BNP Paribas", confirmed_new=True, source="test"
    )
    repo.remember_person(
        full_name="Grace Hopper", current_org="BNP Paribas CIB", confirmed_new=True, source="test"
    )
    with repo.db.connection() as conn:
        names = [
            row["name"] for row in conn.execute("select name from orgs order by name").fetchall()
        ]
    assert names == ["BNP Paribas", "BNP Paribas CIB"]


@pytest.mark.integration
def test_a_merge_decided_once_survives_the_next_import(repo: GraphRepository) -> None:
    # The case this whole change exists for: "2600" and "Ecole 2600" share no key, a human merged
    # them, and the weekly import recreated the loser a few hours later.
    kept = repo.remember_person(
        full_name="Ada Lovelace", current_org="Ecole 2600", confirmed_new=True, source="test"
    )
    with repo.db.connection() as conn:
        keep_id = conn.execute("select id from orgs where name = 'Ecole 2600'").fetchone()["id"]
        drop_id = conn.execute(
            "insert into orgs (name) values ('2600') returning id"
        ).fetchone()["id"]
        conn.execute("select merge_orgs(%s, %s)", (keep_id, drop_id))
        aliases = conn.execute("select alias, org_id from org_aliases").fetchall()
    assert kept["status"] == "created"
    assert aliases == [{"alias": "2600", "org_id": keep_id}]

    repo.remember_person(
        full_name="Grace Hopper", current_org="2600", confirmed_new=True, source="test"
    )
    with repo.db.connection() as conn:
        names = [row["name"] for row in conn.execute("select name from orgs").fetchall()]
        affiliated = conn.execute(
            "select count(*) as n from affiliations where org_id = %s", (keep_id,)
        ).fetchone()["n"]
    assert names == ["Ecole 2600"]
    assert affiliated == 2


@pytest.mark.integration
def test_a_writer_that_never_goes_through_python_is_still_deduplicated(
    repo: GraphRepository,
) -> None:
    # The web client writes through PostgREST, which knows nothing about `_normalize_org_name`.
    with repo.db.connection() as conn:
        conn.execute("insert into orgs (name) values ('ITrust SA')")
        conn.execute("insert into orgs (name) values ('itrust') on conflict (name) do nothing")
        names = [row["name"] for row in conn.execute("select name from orgs").fetchall()]
    assert names == ["ITrust SA"]


@pytest.mark.integration
def test_a_dry_run_says_what_it_would_create(repo: GraphRepository) -> None:
    repo.remember_person(
        full_name="Ada Lovelace", current_org="Armée de Terre", confirmed_new=True, source="test"
    )
    preview = repo.preview_orgs(
        ["armée de terre", "ITrust SA", "ITrust", "", "Armée de Terre", None]
    )
    assert preview["would_create"] == ["ITrust SA"]
    assert preview["resolved"] == {
        "ITrust": "ITrust SA",
        "Armée de Terre": "Armée de Terre",
        "armée de terre": "Armée de Terre",
    }
    assert preview["names"] == 4
