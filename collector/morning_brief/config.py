"""config/*.yaml 로드. 저장소 루트에서 실행하는 것을 전제로 하고, BRIEF_CONFIG_DIR로 바꿀 수 있다."""
import os
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml


def config_dir() -> Path:
    return Path(os.environ.get("BRIEF_CONFIG_DIR", Path.cwd() / "config"))


@cache
def load(name: str) -> dict:
    with open(config_dir() / f"{name}.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass(frozen=True)
class Source:
    name: str
    region: str           # domestic | international
    lang: str
    grp: str | None
    method: str           # rss | sitemap | gnews | api | none
    feed_urls: tuple[str, ...]
    paywall: bool
    has_summary: bool
    tz_naive: bool


def sources() -> list[Source]:
    cfg = load("sources")
    out = []
    for region in ("domestic", "international"):
        for s in cfg[region]:
            urls = s.get("feed_url") or []
            if isinstance(urls, str):
                urls = [urls]
            out.append(Source(
                name=s["name"],
                region=region,
                lang="ko" if region == "domestic" else "en",
                grp=s.get("group"),
                method=s.get("method") or "none",
                feed_urls=tuple(urls),
                paywall=bool(s.get("paywall")),
                has_summary=s.get("has_summary", True),
                tz_naive=bool(s.get("tz_naive")),
            ))
    return out


def ops() -> dict:
    return load("ops")


def user_agent() -> str:
    ua = ops()["collect"]["user_agent"]
    contact = os.environ.get("CONTACT_EMAIL")
    return f"{ua[:-1]}; {contact})" if contact and ua.endswith(")") else ua
