import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row


@contextmanager
def connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL이 설정되지 않았습니다 (.env 또는 GitHub Secrets)")
    with psycopg.connect(url, row_factory=dict_row, autocommit=False) as conn:
        yield conn
