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
        (
            "with gone as (delete from people returning *) "
            "update people set city = 'Paris' where id = 1"
        ),
        "select pg_sleep(10)",
    ],
)
def test_blocks_unsafe_reads_and_writes(query: str) -> None:
    with pytest.raises(ValueError):
        is_write = query.lower().startswith(("delete", "update", "with gone"))
        if is_write and "update" in query.lower():
            guard_write(query)
        else:
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


def test_blocks_ddl_even_when_disguised_in_cte() -> None:
    with pytest.raises(ValueError):
        guard_read("with x as (select 1) create table nope(id int)")
