"""Disposable PostgreSQL schemas for fixtures, examples and offline evaluation."""
from contextlib import contextmanager
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from .db import database_url, initialize


@contextmanager
def temporary_database():
    """Create only a uniquely named schema; drop only that schema on exit.

    Requires CREATE privilege on a development/test database. Never resets existing
    business tables. Returned DSN is process-local and must not be logged.
    """
    url = database_url()
    schema = "acs_test_" + uuid.uuid4().hex
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            isolated_url = make_conninfo(url, options=f"-c search_path={schema}")
            initialize(isolated_url)
            yield isolated_url
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
