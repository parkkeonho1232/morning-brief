"""LLM·임베딩 공통 클라이언트 — 무료 등급만 사용 (CLAUDE.md 스택).

생성: Gemini(tier별 모델) → 429·5xx면 서버가 알려준 대기시간만큼 기다려 재시도 → 길면 Groq.
임베딩: bge-m3(로컬) → 실패 시 그날 전체를 Gemini로(분당 100문장 한도라 느림). 두 모델 벡터는 섞어 쓰지 않는다.
"""
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field

import httpx
import numpy as np

from . import config

GEMINI = "https://generativelanguage.googleapis.com/v1beta"
GROQ = "https://api.groq.com/openai/v1/chat/completions"
MAX_WAIT_S = 65          # 429 retryDelay가 이보다 길면 기다리지 않고 예비 모델로
EMBED_DIM = 1024         # article/event 스키마의 vector(1024), bge-m3와 같은 차원


class LLMError(RuntimeError):
    pass


@dataclass
class Usage:
    calls: dict = field(default_factory=dict)       # "gemini:model" → 횟수
    fallbacks: int = 0
    waits_s: float = 0.0

    def add(self, key: str):
        self.calls[key] = self.calls.get(key, 0) + 1


usage = Usage()
_last_call: dict[str, float] = {}


def _cfg() -> dict:
    return config.ops()["llm"]


def _pace(provider: str):
    """무료 등급 RPM을 넘지 않도록 호출 간 최소 간격을 둔다."""
    gap = _cfg().get("min_interval_s", {}).get(provider, 0)
    wait = _last_call.get(provider, 0) + gap - time.monotonic()
    if wait > 0:
        time.sleep(wait)
        usage.waits_s += wait
    _last_call[provider] = time.monotonic()


def _retry_delay(r: httpx.Response) -> float | None:
    """Gemini 429 응답의 RetryInfo.retryDelay ('37s')."""
    try:
        for d in r.json().get("error", {}).get("details", []):
            if d.get("@type", "").endswith("RetryInfo"):
                return float(d["retryDelay"].rstrip("s"))
    except (ValueError, KeyError, AttributeError):
        pass
    return None


def _extract_json(text: str):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    return json.loads(text)


def _gemini_generate(client: httpx.Client, model: str, prompt: str, schema: dict | None, temperature: float):
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    if schema:
        body["generationConfig"]["responseSchema"] = schema
    for attempt in range(3):
        _pace("gemini")
        r = client.post(f"{GEMINI}/models/{model}:generateContent", params={"key": os.environ["GEMINI_API_KEY"]},
                        json=body, timeout=httpx.Timeout(60.0, connect=10.0))
        if r.status_code in (429, 500, 502, 503, 504):
            delay = _retry_delay(r) or (5 * (attempt + 1))
            if delay > MAX_WAIT_S or attempt == 2:
                raise LLMError(f"gemini {model} HTTP {r.status_code} (retry {delay:.0f}s)")
            time.sleep(delay)
            usage.waits_s += delay
            continue
        if not r.is_success:
            raise LLMError(f"gemini {model} HTTP {r.status_code} {r.text[:200]}")
        usage.add(f"gemini:{model}")
        cands = r.json().get("candidates") or []
        parts = cands[0].get("content", {}).get("parts", []) if cands else []
        text = "".join(p.get("text", "") for p in parts)
        if not text:
            raise LLMError(f"gemini {model} 빈 응답 ({cands[0].get('finishReason') if cands else 'no candidates'})")
        return _extract_json(text)
    raise LLMError("unreachable")


def _groq_generate(client: httpx.Client, model: str, prompt: str, temperature: float):
    for attempt in range(3):
        _pace("groq")
        r = client.post(GROQ, headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"}, timeout=120, json={
            "model": model, "temperature": temperature, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": "Respond with a single valid JSON object only."},
                         {"role": "user", "content": prompt}],
        })
        if r.status_code in (429, 500, 502, 503):
            delay = float(r.headers.get("retry-after") or 5 * (attempt + 1))
            if delay > MAX_WAIT_S or attempt == 2:
                raise LLMError(f"groq {model} HTTP {r.status_code}")
            time.sleep(delay)
            usage.waits_s += delay
            continue
        if not r.is_success:
            raise LLMError(f"groq {model} HTTP {r.status_code} {r.text[:200]}")
        usage.add(f"groq:{model}")
        return _extract_json(r.json()["choices"][0]["message"]["content"])
    raise LLMError("unreachable")


def generate_json(prompt: str, tier: str = "lite", schema: dict | None = None, temperature: float = 0.2):
    """프롬프트 → JSON. tier: 'lite'(번역·판정) | 'main'(사실 추출·카드).

    Groq는 JSON 객체만 반환하므로, 배열이 필요하면 프롬프트에서 {"items": [...]} 형태를 요구할 것.
    """
    cfg = _cfg()
    errors = []
    with httpx.Client() as client:
        if os.environ.get("GEMINI_API_KEY"):
            for model in cfg["gemini"][tier]:
                try:
                    return _gemini_generate(client, model, prompt, schema, temperature)
                except (LLMError, json.JSONDecodeError, httpx.HTTPError) as e:
                    errors.append(str(e)[:160])
        if errors:
            print("llm: Gemini 실패 → 예비 모델 | " + " | ".join(errors), file=sys.stderr)
        if os.environ.get("GROQ_API_KEY"):
            usage.fallbacks += 1
            for model in cfg["groq"]:
                try:
                    return _groq_generate(client, model, prompt, temperature)
                except (LLMError, json.JSONDecodeError, httpx.HTTPError) as e:
                    errors.append(str(e)[:160])
    raise LLMError("모든 모델 실패: " + " | ".join(errors))


# ---------- 임베딩 ----------

def _normalize(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=1, keepdims=True)
    return v / np.where(n == 0, 1, n)


def _gemini_embed(texts: list[str], model: str, task: str) -> np.ndarray:
    out = []
    with httpx.Client(timeout=120) as client:
        for i in range(0, len(texts), 100):
            reqs = [{"model": f"models/{model}", "content": {"parts": [{"text": t[:2000]}]},
                     "taskType": task, "outputDimensionality": EMBED_DIM} for t in texts[i:i + 100]]
            for attempt in range(3):
                _pace("gemini_embed")
                r = client.post(f"{GEMINI}/models/{model}:batchEmbedContents",
                                params={"key": os.environ["GEMINI_API_KEY"]}, json={"requests": reqs})
                if r.status_code in (429, 500, 502, 503, 504):
                    delay = _retry_delay(r) or 5 * (attempt + 1)
                    if delay > MAX_WAIT_S or attempt == 2:
                        raise LLMError(f"gemini embed HTTP {r.status_code}")
                    time.sleep(delay)
                    usage.waits_s += delay
                    continue
                if not r.is_success:
                    raise LLMError(f"gemini embed HTTP {r.status_code} {r.text[:200]}")
                break
            usage.add(f"gemini:{model}")
            out += [e["values"] for e in r.json()["embeddings"]]
    return _normalize(np.array(out, dtype=np.float32))


_bge = None


def _bge_embed(texts: list[str]) -> np.ndarray:
    """bge-m3 로컬 임베딩. 예비용이라 필요할 때만 패키지를 설치한다(GitHub Actions에서 1~2분)."""
    global _bge
    if _bge is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--extra-index-url",
                            "https://download.pytorch.org/whl/cpu", "torch", "sentence-transformers"], check=True)
            from sentence_transformers import SentenceTransformer
        _bge = SentenceTransformer("BAAI/bge-m3", device="cpu")
    usage.add("local:bge-m3")
    return _normalize(np.asarray(_bge.encode(texts, batch_size=32, normalize_embeddings=True), dtype=np.float32))


def embed(texts: list[str], task: str = "CLUSTERING", force_model: str | None = None) -> tuple[np.ndarray, str]:
    """텍스트 → (정규화된 벡터, 모델명). force_model로 같은 날 다른 텍스트도 같은 모델을 쓰게 한다."""
    if not texts:
        return np.zeros((0, EMBED_DIM), dtype=np.float32), force_model or "none"
    gemini = _cfg()["embedding"]["gemini"]
    if force_model in (None, "bge-m3"):
        try:
            return _bge_embed(texts), "bge-m3"
        except Exception as e:                       # 설치·모델 다운로드 실패 등
            if force_model == "bge-m3" or not os.environ.get("GEMINI_API_KEY"):
                raise
            print(f"embed: bge-m3 실패 → Gemini 예비 ({type(e).__name__}: {str(e)[:120]})")
            usage.fallbacks += 1
    return _gemini_embed(texts, gemini, task), gemini
