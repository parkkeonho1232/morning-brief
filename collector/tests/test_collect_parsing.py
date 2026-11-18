from datetime import datetime, timezone

from morning_brief.config import Source
from morning_brief.pipeline.normalize import SUMMARY_MAX, canonical_url, clean_summary, parse_dt, title_hash
from morning_brief.sources.feeds import parse_gnews, parse_rss, parse_sitemap


def src(method="rss", region="domestic", has_summary=True, tz_naive=False):
    return Source("테스트", region, "ko", None, method, (), False, has_summary, tz_naive)


def test_parse_dt_formats():
    utc = datetime(2026, 11, 15, 11, 59, 19, tzinfo=timezone.utc)
    assert parse_dt("Sun, 15 Nov 2026 20:59:19 +0900") == utc
    assert parse_dt("Sun, 15 Nov 2026 20:59:19 +09:00") == utc          # 매일경제 비표준 오프셋
    assert parse_dt("2026-11-15T20:59:19+09:00") == utc
    assert parse_dt("2026-11-15 20:59:19") == utc                       # 시사저널: 시간대 없음 → KST
    assert parse_dt("2026-11-15T11:59:19Z") == utc
    assert parse_dt("") is None and parse_dt("garbage") is None


def test_canonical_url_strips_tracking():
    assert canonical_url("https://News.SBS.co.kr/a?id=1&plink=RSSREADER&utm_source=x#top") == "https://news.sbs.co.kr/a?id=1"


def test_summary_is_capped_to_prevent_full_text():
    s = clean_summary("<p>" + "가" * 2000 + "</p>")
    assert len(s) == SUMMARY_MAX
    assert clean_summary("짧음") is None


def test_clean_text_keeps_korean_title_brackets():
    from morning_brief.pipeline.normalize import clean_text
    assert clean_text("&lt;인간 없는 전쟁&gt; 저자 <b>인터뷰</b>") == "<인간 없는 전쟁> 저자 인터뷰"
    assert clean_text("&lt;p&gt;이중 이스케이프&lt;/p&gt;") == "이중 이스케이프"


def test_title_hash_ignores_spacing_and_punctuation():
    assert title_hash("[속보] 국회, 예산안 통과") == title_hash("[속보]  국회 예산안 통과!")


RSS = b"""<?xml version="1.0" encoding="utf-8"?><rss version="2.0"
 xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>t</title>
<item><title><![CDATA[&quot;\xec\xa0\x9c\xeb\xaa\xa9&quot; A]]></title><link>https://e.com/1?utm_medium=rss</link>
<description><![CDATA[<b>Lead</b> paragraph that is long enough to keep]]></description>
<pubDate>Sun, 15 Nov 2026 20:59:19 +09:00</pubDate></item>
<item><title>B</title><link>https://e.com/2</link><description></description>
<content:encoded><![CDATA[content encoded lead used as summary fallback]]></content:encoded>
<pubDate>2026-11-15 17:16:22</pubDate></item>
<item><title></title><link>https://e.com/3</link></item>
</channel></rss>"""


def test_parse_rss():
    items = parse_rss(RSS, src())
    assert [i.url for i in items] == ["https://e.com/1", "https://e.com/2"]
    assert items[0].title == '"제목" A'
    assert items[0].summary == "Lead paragraph that is long enough to keep"
    assert items[1].summary == "content encoded lead used as summary fallback"
    assert items[1].published_at == datetime(2026, 11, 15, 8, 16, 22, tzinfo=timezone.utc)
    assert all(i.summary is None for i in parse_rss(RSS, src(has_summary=False)))


SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
<url><loc><![CDATA[https://www.ytn.co.kr/_ln/0104_1]]></loc><news:news>
<news:publication><news:name>YTN</news:name><news:language>ko</news:language></news:publication>
<news:publication_date><![CDATA[2026-11-15T20:53:00+09:00]]></news:publication_date>
<news:title><![CDATA[러, 종전협상 입장 선회]]></news:title></news:news></url>
<url><loc>https://x/no-title</loc><lastmod>2026-11-15</lastmod></url>
</urlset>""".encode()


def test_parse_sitemap():
    items = parse_sitemap(SITEMAP, src("sitemap"))
    assert len(items) == 1
    assert items[0].title == "러, 종전협상 입장 선회"
    assert items[0].summary is None
    assert items[0].published_at == datetime(2026, 11, 15, 11, 53, tzinfo=timezone.utc)


GNEWS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>g</title>
<item><title>세무사 수석 합격자 자수 - 한겨레</title><link>https://news.google.com/rss/articles/abc</link>
<pubDate>Sun, 15 Nov 2026 12:00:00 GMT</pubDate><description>&lt;a href="x"&gt;html&lt;/a&gt;</description>
<source url="https://www.hani.co.kr">한겨레</source></item></channel></rss>""".encode()


def test_parse_gnews_strips_outlet_suffix():
    items = parse_gnews(GNEWS, src("gnews"))
    assert items[0].title == "세무사 수석 합격자 자수"
    assert items[0].summary is None
    assert items[0].url == "https://news.google.com/rss/articles/abc"


def test_junk_titles_are_filtered():
    from morning_brief.pipeline.normalize import is_junk_title
    for t in ["최신 뉴스", "뉴스데스크", "[뉴스9 충북 클로징]", "스포츠", "[뉴스9 부산 클로징]", "뉴스투데이", "11월 15일 '뉴스 7' 클로징"]:
        assert is_junk_title(t), t
    for t in ["한국 야구, APBC 결승서 일본에 1-5 패배…3회 연속 준우승", "굽네치킨 부당지원 의혹 조사"]:
        assert not is_junk_title(t), t
