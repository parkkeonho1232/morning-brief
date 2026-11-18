"""기준일의 사건·새 사실을 사람이 읽기 좋게 출력 (품질 점검용)."""
from datetime import date

from . import db


def run(d: date) -> int:
    with db.connect() as conn:
        events = conn.execute("""
            select e.id, e.title, e.verification, e.first_seen_date,
                   (select count(*) from cluster c where c.event_id = e.id and c.base_date = %s) as clusters,
                   (select max(n_sources) from cluster c where c.event_id = e.id and c.base_date = %s) as sources
            from event e where e.last_change_date = %s order by sources desc nulls last
        """, (d, d, d)).fetchall()
        print(f"== {d} 사건 {len(events)}개")
        for e in events:
            print(f"\n[{e['id']}] {e['title']}  ({e['verification']}, 매체 {e['sources']}, 최초 {e['first_seen_date']})")
            for f in conn.execute("""select fact, change_type, article_ids, needs_review from event_fact
                                     where event_id = %s and first_seen_date = %s order by id""", (e["id"], d)):
                srcs = conn.execute("""select string_agg(distinct s.name, ',') as s from article a join source s
                                       on s.id = a.source_id where a.id = any(%s)""", (f["article_ids"],)).fetchone()["s"]
                flag = " ⚠자동판정" if f["needs_review"] else ""
                print(f"   - [{f['change_type']}] {f['fact']}  ← {srcs}{flag}")

        cards = conn.execute("select kind, rank, body from card where base_date = %s order by kind desc, rank", (d,)).fetchall()
        print(f"\n== {d} 카드 {len(cards)}장 (인물 후보)")
        for c in cards:
            b = c["body"]
            print(f"\n<{c['kind']} {c['rank']}> {b['title']}")
            for p in b.get("people") or []:
                print(f"   기사 속: {p['name']} ({p.get('role') or '-'}) — {p.get('why') or ''}")
            for v in b.get("videos") or []:
                print(f"   유튜브: {v['channel']} · {v['title']} (조회 {v.get('views')})")
            for p in b.get("ai_suggestions") or []:
                print(f"   AI 추천: {p['name']} ({p.get('role') or '-'}) — {p.get('why') or ''}")
    return 0
