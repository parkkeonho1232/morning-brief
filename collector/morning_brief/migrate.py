"""supabase/migrations/*.sql을 순서대로 한 번씩 적용한다. 적용 기록은 schema_migrations 테이블."""
import os
from pathlib import Path

from . import db

# 수동으로 적용된 마이그레이션 감지용: 각 파일이 만드는 대표 테이블·컬럼
_FINGERPRINT = {
    "0001_init.sql": "select to_regclass('public.source') is not null",
    "0002_collect.sql": "select to_regclass('public.feed_state') is not null",
}


def migrations_dir() -> Path:
    return Path(os.environ.get("BRIEF_MIGRATIONS_DIR", Path.cwd() / "supabase" / "migrations"))


def run() -> int:
    files = sorted(migrations_dir().glob("*.sql"))
    with db.connect() as conn:
        conn.execute("""create table if not exists schema_migrations (
                          name text primary key, applied_at timestamptz not null default now())""")
        applied = {r["name"] for r in conn.execute("select name from schema_migrations")}
        if not applied:
            for name, probe in _FINGERPRINT.items():
                if conn.execute(probe).fetchone()["?column?"]:
                    conn.execute("insert into schema_migrations (name) values (%s)", (name,))
                    applied.add(name)
                    print(f"migrate: {name} 이미 적용됨 (감지)")
        conn.commit()
        for f in files:
            if f.name in applied:
                continue
            conn.execute(f.read_text(encoding="utf-8"))
            conn.execute("insert into schema_migrations (name) values (%s)", (f.name,))
            conn.commit()
            print(f"migrate: {f.name} 적용")
    print(f"migrate: 최신 ({len(files)}개)")
    return 0
