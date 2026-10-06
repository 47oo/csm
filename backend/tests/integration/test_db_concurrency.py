"""Concurrency prerequisite tests (TD-2 V7/B5/B6).

These prove the fixture can drive multiple real connections, real commits and a
final persistence assertion — the prerequisite for T07/T35. They are NOT
business concurrency cases (F001 has no business write path).
"""

from __future__ import annotations

from sqlalchemy import text

PROBE_TABLE = "_f001_concurrency_probe"


def _drop_probe(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS public."{PROBE_TABLE}"'))


def test_committed_writes_visible_across_connections(committed_engine):
    """B5/B6: two independent committed connections are observed by a new one."""
    engine = committed_engine
    _drop_probe(engine)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    f'CREATE TABLE public."{PROBE_TABLE}" '
                    "(id integer PRIMARY KEY, note text NOT NULL)"
                )
            )

        # Two connections each open their own transaction and really commit.
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(
                    text(f'INSERT INTO public."{PROBE_TABLE}" (id, note) VALUES (1, :n)'),
                    {"n": "one"},
                )
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(
                    text(f'INSERT INTO public."{PROBE_TABLE}" (id, note) VALUES (2, :n)'),
                    {"n": "two"},
                )

        # A brand-new connection observes the committed union.
        with engine.connect() as conn:
            rows = conn.execute(
                text(f'SELECT id, note FROM public."{PROBE_TABLE}" ORDER BY id')
            ).all()
        assert rows == [(1, "one"), (2, "two")]

        # Close all pooled connections and re-read: state is truly persisted.
        engine.dispose()
        with engine.connect() as conn:
            count = conn.execute(
                text(f'SELECT count(*) FROM public."{PROBE_TABLE}"')
            ).scalar()
        assert count == 2
    finally:
        _drop_probe(engine)


def test_uncommitted_write_is_not_visible(committed_engine):
    """B5: an uncommitted transaction must not be visible to another connection."""
    engine = committed_engine
    _drop_probe(engine)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    f'CREATE TABLE public."{PROBE_TABLE}" '
                    "(id integer PRIMARY KEY, note text NOT NULL)"
                )
            )

        writer = engine.connect()
        try:
            transaction = writer.begin()
            writer.execute(
                text(f'INSERT INTO public."{PROBE_TABLE}" (id, note) VALUES (99, :n)'),
                {"n": "uncommitted"},
            )
            with engine.connect() as reader:
                visible = reader.execute(
                    text(f'SELECT count(*) FROM public."{PROBE_TABLE}"')
                ).scalar()
            assert visible == 0
            transaction.rollback()
        finally:
            writer.close()

        with engine.connect() as conn:
            assert (
                conn.execute(text(f'SELECT count(*) FROM public."{PROBE_TABLE}"')).scalar()
                == 0
            )
    finally:
        _drop_probe(engine)