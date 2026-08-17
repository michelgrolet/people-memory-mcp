import pytest

from people_memory.sql_guard import guard_read, guard_write


@pytest.mark.parametrize(
    "query",
    [
        "select * from people",
        "with recent as (select * from interactions) select * from recent",
        "select ';' as harmless_semicolon",
    ],
)
def test_allows_single_reads(query: str) -> None:
    assert guard_read(query)


@pytest.mark.parametrize(
    "query",
    [
        "delete from people",
        "update people set city = 'Paris'",
        "drop table people",
        "select 1; select 2",
        "with gone as (delete from people returning *) select * from gone",
        "select pg_sleep(10)",
        # Parses as a SELECT, and writes a table.
        "select * into evil from people",
        "select id into evil from people where id = 1",
    ],
)
def test_read_rejects_anything_that_is_not_one_plain_select(query: str) -> None:
    with pytest.raises(ValueError):
        guard_read(query)


@pytest.mark.parametrize(
    "query",
    [
        "insert into facts (person_id, key) values (1, 'likes')",
        "update people set city = 'Paris' where id = 1",
        "delete from people where id = 1",
    ],
)
def test_allows_guarded_writes(query: str) -> None:
    assert guard_write(query)


@pytest.mark.parametrize(
    "query",
    [
        # The rule worth testing on its own: an UPDATE or DELETE with no WHERE takes the whole
        # table. Each of these has to reach guard_write to prove guard_write is what stops it.
        "delete from people",
        "update people set city = 'Paris'",
        "drop table people",
        "select * from people",
        "select 1; select 2",
        "with gone as (delete from people returning *) "
        "update people set city = 'Paris' where id = 1",
        "delete from people where id = 1; delete from orgs where id = 1",
        "update people set city = 'Paris' where id = 1 and pg_sleep(10) is null",
    ],
)
def test_write_rejects_unguarded_and_multiple_operations(query: str) -> None:
    with pytest.raises(ValueError):
        guard_write(query)


def test_blocks_ddl_even_when_disguised_in_cte() -> None:
    with pytest.raises(ValueError):
        guard_read("with x as (select 1) create table nope(id int)")
