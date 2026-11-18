"""API 키 점검: 각 서비스에 가장 가벼운 요청을 보내 키가 유효한지만 확인한다. 키 값은 출력하지 않는다."""
import os

import httpx

from . import config


def _env(name: str) -> str | None:
    return os.environ.get(name) or None


def _gemini(c: httpx.Client, key: str) -> str:
    r = c.get("https://generativelanguage.googleapis.com/v1beta/models", params={"key": key, "pageSize": 50})
    if not r.is_success:
        return f"FAIL HTTP {r.status_code} {r.json().get('error', {}).get('message', '')[:120]}"
    flash = [m["name"].split("/")[-1] for m in r.json().get("models", []) if "flash" in m["name"]]
    return f"OK (flash 모델 {len(flash)}개: {', '.join(flash[:4])})"


def _groq(c: httpx.Client, key: str) -> str:
    r = c.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {key}"})
    if not r.is_success:
        return f"FAIL HTTP {r.status_code}"
    ids = [m["id"] for m in r.json().get("data", [])]
    return f"OK (모델 {len(ids)}개: {', '.join(ids[:4])})"


def _youtube(c: httpx.Client, key: str) -> str:
    cid = config.load("youtube_channels")["channels"][0]["channel_id"]
    r = c.get("https://www.googleapis.com/youtube/v3/channels", params={"part": "snippet", "id": cid, "key": key})
    if not r.is_success:
        return f"FAIL HTTP {r.status_code} {r.json().get('error', {}).get('message', '')[:120]}"
    items = r.json().get("items", [])
    return f"OK ({items[0]['snippet']['title']})" if items else "FAIL 채널 조회 결과 없음"


def _assembly(c: httpx.Client, key: str) -> str:
    r = c.get("https://open.assembly.go.kr/portal/openapi/ALLSCHEDULE",
              params={"KEY": key, "Type": "json", "pIndex": 1, "pSize": 1})
    text = r.text[:400]
    if "INFO-000" in text:
        return "OK"
    code = next((m for m in ("ERROR-290", "ERROR-300", "ERROR-310", "INFO-200", "INFO-300") if m in text), None)
    return f"{'OK (조회 결과 없음)' if code == 'INFO-200' else 'FAIL'} HTTP {r.status_code} {code or text[:120]}"


CHECKS = [
    ("GEMINI_API_KEY", _gemini),
    ("GROQ_API_KEY", _groq),
    ("YOUTUBE_API_KEY", _youtube),
    ("ASSEMBLY_API_KEY", _assembly),
]


def embed_quota() -> None:
    """임베딩 무료 한도 확인: 100건 묶음을 연속 호출해 429 응답의 한도 정보를 출력."""
    import json as _json
    model = config.ops()["llm"]["embedding"]["gemini"]
    reqs = [{"model": f"models/{model}", "content": {"parts": [{"text": f"테스트 문장 {i}"}]},
             "outputDimensionality": 1024} for i in range(100)]
    with httpx.Client(timeout=60) as c:
        for n in range(1, 6):
            r = c.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents",
                       params={"key": os.environ["GEMINI_API_KEY"]}, json={"requests": reqs})
            print(f"batch {n}: HTTP {r.status_code}")
            if r.status_code == 429:
                for d in r.json().get("error", {}).get("details", []):
                    print("  ", _json.dumps(d, ensure_ascii=False)[:500])
                break


def llm_smoke() -> None:
    """실제 키로 생성(JSON)·임베딩이 동작하는지 확인."""
    from . import llm
    r = llm.generate_json('다음 제목을 한국어로 번역해 {"title_ko": "..."} 로만 답하라: "Fed holds rates steady"')
    print("generate lite:", r, llm.usage.calls)
    r = llm.generate_json('{"ok": true} 를 그대로 출력하라', tier="main")
    print("generate main:", r, llm.usage.calls)
    v, model = llm.embed(["기준금리 동결", "한은, 기준금리 연 2.5%로 동결", "프로야구 한국시리즈 우승"])
    sims = (v @ v.T).round(3).tolist()
    print(f"embed: model={model} shape={v.shape} sims={sims}")


def list_models() -> None:
    """Gemini·Groq에서 실제 쓸 수 있는 모델 이름 확인용."""
    with httpx.Client(timeout=20) as c:
        r = c.get("https://generativelanguage.googleapis.com/v1beta/models",
                  params={"key": os.environ["GEMINI_API_KEY"], "pageSize": 200})
        for m in r.json().get("models", []):
            methods = m.get("supportedGenerationMethods", [])
            if "embedContent" in methods or "generateContent" in methods:
                print(f"gemini {m['name'].split('/')[-1]:<40} {','.join(methods)[:60]} in={m.get('inputTokenLimit')}")
        r = c.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"})
        for m in r.json().get("data", []):
            print(f"groq   {m['id']:<40} ctx={m.get('context_window')} active={m.get('active')}")


def probe_assembly() -> None:
    """국회 일정 API 원본 형식 확인용: 앞으로 7일 중 일정이 있는 날의 첫 행 필드를 출력."""
    from datetime import date, timedelta
    from .sources.schedules import fetch_assembly_raw
    with httpx.Client(timeout=20, headers={"User-Agent": config.user_agent()}) as c:
        r = c.get("https://open.assembly.go.kr/portal/openapi/ALLSCHEDULE",
                  params={"KEY": os.environ["ASSEMBLY_API_KEY"], "Type": "json", "pIndex": 1, "pSize": 2})
        print("no-date sample:", r.text.replace(os.environ["ASSEMBLY_API_KEY"], "***")[:900])
        for i in range(8):
            d = date.today() + timedelta(days=i)
            rows = fetch_assembly_raw(c, d)
            print(f"{d}: rows={len(rows)}")
            if rows:
                print("  fields:", {k: str(v)[:60] for k, v in rows[0].items()})


def run() -> int:
    failed = 0
    with httpx.Client(timeout=20, headers={"User-Agent": config.user_agent()}) as c:
        for name, fn in CHECKS:
            key = _env(name)
            if not key:
                print(f"- {name:<18} 없음")
                failed += 1
                continue
            try:
                result = fn(c, key.strip())
            except Exception as e:
                result = f"FAIL {type(e).__name__}: {str(e)[:120]}"
            # 혹시라도 키가 메시지에 섞여 나오지 않도록 마스킹
            result = result.replace(key.strip(), "***")
            failed += not result.startswith("OK")
            print(f"{'✓' if result.startswith('OK') else '✗'} {name:<18} {result}")
    return 1 if failed else 0
