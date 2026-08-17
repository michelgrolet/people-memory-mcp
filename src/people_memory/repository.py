from __future__ import annotations

import re
import unicodedata
from datetime import date
from difflib import SequenceMatcher
from typing import Any

from psycopg import sql

from .dates import normalize_partial_date
from .db import Database
from .sql_guard import guard_read, guard_write

PERSON_FIELDS = {
    "full_name",
    "first_name",
    "last_name",
    "birthdate",
    "birthday_md",
    "city",
    "country",
    "current_org",
    "current_role",
    "linkedin_url",
    "tie_strength",
    "met_where",
    "met_when",
    "summary",
}


def _normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(re.findall(r"[a-z0-9]+", without_marks))


def _conflicts_with(key: str, existing: Any, incoming: Any) -> bool:
    """Whether a stored value and an incoming one genuinely disagree.

    `linkedin_url` is an identifier wearing a column, and a URL's case carries no meaning. Comparing
    it verbatim made the same profile, retyped or re-exported in another case, come back as
    needs_confirmation, which is a dead end for any importer that does not control casing.
    """
    if existing in (None, "", incoming):
        return False
    if key == "linkedin_url":
        return str(existing).strip().lower() != str(incoming).strip().lower()
    return True


def _normalize_identifier(value: str) -> str:
    """Identifiers are matched case-insensitively, so they are stored that way.

    Lookup has always compared `lower(i.value)`, while writing lowercased `email` alone. The gap
    let two rows differ by case, which the `(kind, value)` primary key could not see as one, and a
    person matching both was returned as two candidates and could never be resolved again. The
    database now carries the same rule as a check constraint.
    """
    return value.strip().lower()


def _name_similarity(left: str, right: str) -> float:
    left_normalized = _normalize_name(left)
    right_normalized = _normalize_name(right)
    if not left_normalized or not right_normalized:
        return 0.0
    direct = SequenceMatcher(None, left_normalized, right_normalized).ratio()
    left_sorted = " ".join(sorted(left_normalized.split()))
    right_sorted = " ".join(sorted(right_normalized.split()))
    reordered = SequenceMatcher(None, left_sorted, right_sorted).ratio()
    return max(direct, reordered)


class GraphRepository:
    def __init__(self, db: Database):
        self.db = db

    def status(self) -> dict[str, Any]:
        counts = self.db.fetch_one(
            """
            select
              (select count(*) from people) as people,
              (select count(*) from orgs) as organizations,
              (select count(*) from edges) as relationships,
              (select count(*) from facts) as facts,
              (select count(*) from interactions) as interactions
            """
        )
        return {"ok": True, **(counts or {})}

    def search_people(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        needle = f"%{query.strip()}%"
        return self.db.fetch_all(
            """
            select p.id, p.full_name, p.current_org, p."current_role", p.city, p.country,
                   p.tie_strength, p.summary, p.last_contact, p.days_since_contact
            from person p
            where p.full_name ilike %s
               or coalesce(p.current_org, '') ilike %s
               or coalesce(p."current_role", '') ilike %s
               or coalesce(p.city, '') ilike %s
               or coalesce(p.summary, '') ilike %s
               or exists (
                   select 1 from identifiers i
                   where i.person_id = p.id and i.value ilike %s
               )
               or exists (
                   select 1 from facts f
                   where f.person_id = p.id
                     and (f.key ilike %s or coalesce(f.value, '') ilike %s)
               )
            order by
              case when lower(p.full_name) = lower(%s) then 0 else 1 end,
              coalesce(p.tie_strength, 0) desc,
              p.full_name
            limit %s
            """,
            (
                needle,
                needle,
                needle,
                needle,
                needle,
                needle,
                needle,
                needle,
                query.strip(),
                min(max(limit, 1), 100),
            ),
        )

    def _person_candidates(
        self,
        conn,
        full_name: str,
        email: str | None = None,
        phone: str | None = None,
        linkedin_url: str | None = None,
    ) -> list[dict[str, Any]]:
        if email or phone or linkedin_url:
            identifiers = [("email", email), ("phone", phone), ("linkedin", linkedin_url)]
            identifiers = [
                (kind, _normalize_identifier(value)) for kind, value in identifiers if value
            ]
            for kind, value in identifiers:
                rows = list(
                    conn.execute(
                        """
                        select p.id, p.full_name, p.current_org, p.city
                        from people p join identifiers i on i.person_id = p.id
                        -- Plain equality, not lower(i.value): stored values are lowercase by
                        -- check constraint, so this is the same match and it uses the primary key.
                        where i.kind = %s and i.value = %s
                        """,
                        (kind, value),
                    ).fetchall()
                )
                if rows:
                    return rows
        return list(
            conn.execute(
                """
                select id, full_name, current_org, city
                from people where lower(full_name) = lower(%s)
                order by id
                """,
                (full_name.strip(),),
            ).fetchall()
        )

    def resolve_person(self, name: str) -> dict[str, Any]:
        candidates = self.db.fetch_all(
            """
            select id, full_name, current_org, "current_role", city
            from people
            where lower(full_name) = lower(%s) or full_name ilike %s
            order by case when lower(full_name) = lower(%s) then 0 else 1 end,
                     coalesce(tie_strength, 0) desc, full_name
            limit 10
            """,
            (name.strip(), f"%{name.strip()}%", name.strip()),
        )
        exact = [
            row for row in candidates if row["full_name"].casefold() == name.strip().casefold()
        ]
        if len(exact) == 1:
            return {"status": "resolved", "person": exact[0]}
        if not candidates:
            return {"status": "not_found", "query": name}
        # A single fuzzy (non-exact) candidate is still a guess, not a resolution:
        # it must go through needs_confirmation just like remember_person does.
        return {"status": "needs_confirmation", "query": name, "candidates": candidates}

    def get_person(self, person_id: int) -> dict[str, Any] | None:
        person = self.db.fetch_one("select * from person where id = %s", (person_id,))
        if not person:
            return None
        person["identifiers"] = self.db.fetch_all(
            """
            select kind, value, is_primary
            from identifiers where person_id = %s order by kind, value
            """,
            (person_id,),
        )
        person["facts"] = self.db.fetch_all(
            """
            select id, key, value, num, date, source, observed_at, confidence
            from facts where person_id = %s order by observed_at desc, id desc
            """,
            (person_id,),
        )
        person["interactions"] = self.db.fetch_all(
            """
            select id, happened_on, channel, summary, source
            from interactions where person_id = %s order by happened_on desc, id desc limit 100
            """,
            (person_id,),
        )
        person["affiliations"] = self.db.fetch_all(
            """
            select a.org_id, o.name as organization, a.role, a.since, a.until, a.source
            from affiliations a join orgs o on o.id = a.org_id
            where a.person_id = %s order by (a.until is null) desc, a.since desc nulls last
            """,
            (person_id,),
        )
        person["relationships"] = self.db.fetch_all(
            """
            select r.other_id as person_id, p.full_name, r.kind, r.strength,
                   r.since, r.until, r.note
            from rel r join people p on p.id = r.other_id
            where r.person_id = %s order by coalesce(r.strength, 0) desc, p.full_name
            """,
            (person_id,),
        )
        return person

    def remember_person(
        self,
        *,
        full_name: str,
        email: str | None = None,
        phone: str | None = None,
        current_org: str | None = None,
        current_role: str | None = None,
        linkedin_url: str | None = None,
        city: str | None = None,
        country: str | None = None,
        summary: str | None = None,
        birthdate: date | str | None = None,
        birthday_md: str | None = None,
        fact_key: str | None = None,
        fact_value: str | None = None,
        source: str = "agent",
        confirmed_new: bool = False,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        full_name = full_name.strip()
        if not full_name:
            raise ValueError("full_name is required")
        with self.db.transaction() as conn:
            candidates = self._person_candidates(conn, full_name, email, phone, linkedin_url)
            if len(candidates) > 1:
                return {
                    "status": "needs_confirmation",
                    "reason": "More than one person matches. Ask the user which one.",
                    "candidates": candidates,
                }
            if candidates and candidates[0]["full_name"].casefold() != full_name.casefold():
                return {
                    "status": "needs_confirmation",
                    "reason": (
                        "An email or phone belongs to a person with a different name. "
                        "Ask whether they are the same person before changing anything."
                    ),
                    "incoming": {
                        "full_name": full_name,
                        "email": email,
                        "phone": phone,
                        "linkedin_url": linkedin_url,
                    },
                    "candidates": candidates,
                }
            if not candidates and not confirmed_new:
                people = conn.execute(
                    "select id, full_name, current_org, city from people"
                ).fetchall()
                similar = []
                for person in people:
                    similarity = _name_similarity(person["full_name"], full_name)
                    if similarity >= 0.78:
                        similar.append({**person, "similarity": similarity})
                similar.sort(key=lambda person: person["similarity"], reverse=True)
                similar = similar[:5]
                if similar:
                    return {
                        "status": "needs_confirmation",
                        "reason": (
                            "A similar name already exists. Ask whether this is that person or "
                            "a new one."
                        ),
                        "candidates": similar,
                    }

            fields = {
                "current_org": current_org,
                "current_role": current_role,
                "linkedin_url": linkedin_url,
                "city": city,
                "country": country,
                "summary": summary,
                "birthdate": birthdate,
                "birthday_md": birthday_md,
            }
            if candidates:
                person_id = candidates[0]["id"]
                existing = conn.execute(
                    "select * from people where id = %s", (person_id,)
                ).fetchone()
                conflicts = {
                    key: {"existing": existing[key], "incoming": value}
                    for key, value in fields.items()
                    if value is not None and _conflicts_with(key, existing.get(key), value)
                }
                if conflicts and not overwrite:
                    return {
                        "status": "needs_confirmation",
                        "reason": (
                            "New information conflicts with stored values. Ask before overwriting."
                        ),
                        "person": candidates[0],
                        "conflicts": conflicts,
                    }
                updates = {key: value for key, value in fields.items() if value is not None}
                if updates:
                    assignments = sql.SQL(", ").join(
                        sql.SQL("{} = {}").format(sql.Identifier(key), sql.Placeholder())
                        for key in updates
                    )
                    conn.execute(
                        sql.SQL("update people set {}, updated_at = now() where id = %s").format(
                            assignments
                        ),
                        (*updates.values(), person_id),
                    )
                created = False
            else:
                person_id = conn.execute(
                    """
                    insert into people (
                      full_name, current_org, "current_role", linkedin_url,
                      city, country, summary, birthdate, birthday_md
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning id
                    """,
                    (
                        full_name,
                        current_org,
                        current_role,
                        linkedin_url,
                        city,
                        country,
                        summary,
                        birthdate,
                        birthday_md,
                    ),
                ).fetchone()["id"]
                created = True

            for kind, value in (
                ("email", email),
                ("phone", phone),
                ("linkedin", linkedin_url),
            ):
                if value:
                    normalized = _normalize_identifier(value)
                    conn.execute(
                        """
                        insert into identifiers (person_id, kind, value, source)
                        values (%s, %s, %s, %s)
                        on conflict (kind, value) do nothing
                        """,
                        (person_id, kind, normalized, source),
                    )
            if current_org:
                org_id = conn.execute(
                    """
                    insert into orgs (name) values (%s)
                    on conflict (name) do update set name = excluded.name returning id
                    """,
                    (current_org,),
                ).fetchone()["id"]
                conn.execute(
                    """
                    insert into affiliations (person_id, org_id, role, source)
                    values (%s, %s, %s, %s)
                    on conflict (person_id, org_id, role) do nothing
                    """,
                    (person_id, org_id, current_role or "", source),
                )
            if fact_key:
                conn.execute(
                    """
                    insert into facts (person_id, key, value, source, confidence)
                    values (%s, %s, %s, %s, 'stated')
                    on conflict (
                        person_id, key, value,
                        coalesce(date, ''),
                        coalesce(num, 'NaN'::double precision)
                    ) where value is not null do nothing
                    """,
                    (person_id, fact_key, fact_value, source),
                )
            return {
                "status": "created" if created else "updated",
                "person": self._person_summary(conn, person_id),
            }

    def add_identifier(
        self, person_id: int, kind: str, value: str, source: str = "agent"
    ) -> dict[str, Any]:
        normalized = _normalize_identifier(value)
        if not normalized:
            raise ValueError("identifier value is required")
        with self.db.transaction() as conn:
            existing = conn.execute(
                "select person_id from identifiers where kind = %s and value = %s",
                (kind, normalized),
            ).fetchone()
            if existing and existing["person_id"] != person_id:
                return {
                    "status": "needs_confirmation",
                    "reason": "This identifier already belongs to another person.",
                    "kind": kind,
                    "value": normalized,
                    "existing_person_id": existing["person_id"],
                }
            row = conn.execute(
                """
                insert into identifiers (person_id, kind, value, source)
                values (%s, %s, %s, %s)
                on conflict (kind, value) do nothing
                returning person_id, kind, value, source
                """,
                (person_id, kind, normalized, source),
            ).fetchone()
            if row:
                return {"status": "created", "identifier": row}
            owner = conn.execute(
                """
                select person_id, kind, value, source
                from identifiers where kind = %s and value = %s
                """,
                (kind, normalized),
            ).fetchone()
            if owner and owner["person_id"] == person_id:
                return {"status": "exists", "identifier": owner}
            return {
                "status": "needs_confirmation",
                "reason": "This identifier was concurrently assigned to another person.",
                "kind": kind,
                "value": normalized,
                "existing_person_id": owner["person_id"] if owner else None,
            }

    @staticmethod
    def _person_summary(conn, person_id: int) -> dict[str, Any]:
        return conn.execute(
            """
            select id, full_name, current_org, "current_role", city, country,
                   tie_strength, summary
            from people where id = %s
            """,
            (person_id,),
        ).fetchone()

    def add_fact(
        self,
        person_id: int,
        key: str,
        value: str | None,
        *,
        num: float | None = None,
        fact_date: date | str | None = None,
        source: str = "agent",
        confidence: str = "stated",
    ) -> dict[str, Any]:
        fact_date = normalize_partial_date(fact_date)
        row = self.db.fetch_one(
            """
            insert into facts (person_id, key, value, num, date, source, confidence)
            values (%s, %s, %s, %s, %s, %s, %s)
            on conflict (
                person_id, key, value,
                coalesce(date, ''),
                coalesce(num, 'NaN'::double precision)
            ) where value is not null do nothing
            returning *
            """,
            (person_id, key, value, num, fact_date, source, confidence),
        )
        if row is None and value is not None:
            row = self.db.fetch_one(
                """
                select * from facts
                where person_id = %s and key = %s and value = %s
                  and date is not distinct from %s
                  and num is not distinct from %s
                """,
                (person_id, key, value, fact_date, num),
            )
        return row or {}

    def record_interaction(
        self,
        person_id: int,
        happened_on: date,
        channel: str,
        summary: str | None,
        source: str = "agent",
    ) -> dict[str, Any]:
        row = self.db.fetch_one(
            """
            insert into interactions (person_id, happened_on, channel, summary, source)
            values (%s, %s, %s, %s, %s) returning *
            """,
            (person_id, happened_on, channel, summary, source),
        )
        return row or {}

    def connect_people(
        self,
        a_id: int,
        b_id: int,
        kind: str,
        *,
        strength: int | None = None,
        note: str | None = None,
        source: str = "agent",
    ) -> dict[str, Any]:
        if a_id == b_id:
            raise ValueError("A person cannot be connected to themselves.")
        row = self.db.fetch_one(
            """
            insert into edges (a_id, b_id, kind, strength, note, source)
            values (%s, %s, %s, %s, %s, %s)
            on conflict (a_id, b_id, kind) do update
              set strength = coalesce(excluded.strength, edges.strength),
                  note = coalesce(excluded.note, edges.note),
                  source = excluded.source,
                  observed_at = current_date
            returning *
            """,
            (a_id, b_id, kind, strength, note, source),
        )
        return row or {}

    def stale_contacts(self, min_days: int = 180, limit: int = 30) -> list[dict[str, Any]]:
        return self.db.fetch_all(
            """
            select * from stale
            where days_since_contact >= %s
            order by tie_strength desc nulls last, days_since_contact desc
            limit %s
            """,
            (min_days, min(max(limit, 1), 200)),
        )

    def find_intro_path(
        self, target_org: str, from_person: str, max_depth: int = 3
    ) -> list[dict[str, Any]]:
        return self.db.fetch_all(
            "select * from find_intro_paths(%s, %s, %s)",
            (from_person, target_org, min(max(max_depth, 1), 5)),
        )

    def graph_snapshot(self, limit: int = 5000) -> dict[str, Any]:
        capped = min(limit, 10_000)
        return {
            "people": self.db.fetch_all(
                "select * from person order by full_name limit %s", (capped,)
            ),
            "organizations": self.db.fetch_all(
                "select * from orgs order by name limit %s", (capped,)
            ),
            "relationships": self.db.fetch_all(
                "select * from edges order by a_id, b_id limit %s", (capped * 2,)
            ),
            "affiliations": self.db.fetch_all("select * from affiliations limit %s", (capped * 2,)),
        }

    def create_person(self, values: dict[str, Any]) -> dict[str, Any]:
        cleaned = {
            key: value
            for key, value in values.items()
            if key in PERSON_FIELDS and value is not None
        }
        if not cleaned.get("full_name"):
            raise ValueError("full_name is required")
        columns = sql.SQL(", ").join(map(sql.Identifier, cleaned))
        placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in cleaned)
        with self.db.connection() as conn:
            return conn.execute(
                sql.SQL("insert into people ({}) values ({}) returning *").format(
                    columns, placeholders
                ),
                tuple(cleaned.values()),
            ).fetchone()

    def update_person(self, person_id: int, values: dict[str, Any]) -> dict[str, Any] | None:
        cleaned = {key: value for key, value in values.items() if key in PERSON_FIELDS}
        if not cleaned:
            return self.db.fetch_one("select * from people where id = %s", (person_id,))
        assignments = sql.SQL(", ").join(
            sql.SQL("{} = {}").format(sql.Identifier(key), sql.Placeholder()) for key in cleaned
        )
        with self.db.connection() as conn:
            return conn.execute(
                sql.SQL(
                    "update people set {}, updated_at = now() where id = %s returning *"
                ).format(assignments),
                (*cleaned.values(), person_id),
            ).fetchone()

    def delete_person(self, person_id: int) -> bool:
        row = self.db.fetch_one("select delete_person(%s) as deleted", (person_id,))
        return bool(row and row["deleted"])

    def read_query(self, query: str, max_rows: int = 500) -> list[dict[str, Any]]:
        guarded = guard_read(query)
        return self.db.fetch_read_only(guarded, min(max(max_rows, 1), 2000))

    def write_query(self, query: str) -> dict[str, Any]:
        guarded = guard_write(query)
        with self.db.connection() as conn:
            cursor = conn.execute(guarded)
            rows = list(cursor.fetchall()) if cursor.description else []
            return {"row_count": cursor.rowcount, "rows": rows[:500]}
