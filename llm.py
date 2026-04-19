import json
import os
import threading
import requests

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))

PROMPT_TEMPLATE = """\
You are a professional news editor. Given the headline and article below, return a JSON object with EXACTLY these keys:

{{
  "headline": "<rewritten headline>",
  "categories": ["<primary>", "<optional secondary>"],
  "tags": ["<tag1>", "<tag2>", "<tag3>"],
  "summary": "<60-65 word summary>",
  "word_count": <integer>,
  "qa_pass": <true|false>
}}

------------------------
HEADLINE RULES:
- Maximum 12 words
- Must include WHO + WHAT
- Use strong, precise present-tense verbs (e.g. says, warns, approves, rejects)
- AP/Reuters style — factual, no clickbait
- Remove filler phrases like "when it comes to", "regarding", "related to"
- Use quotes ONLY if central to the story
- Avoid vague words like "issue", "situation", "concerns"

------------------------
CATEGORY RULES:
- Select ONLY from this list:
  ["politics","policy","elections","law","economy","markets","banking","business","corporate",
  "technology","ai","cybersecurity","health","science","environment","world","diplomacy",
  "defense","energy","society","education","immigration","sports"]
- Choose 1-3 maximum
- Do NOT create new categories
- Prefer the most specific applicable ones

------------------------
TAG RULES:
- Extract 3-6 tags
- Include:
  - key entities (people, countries, organizations)
  - key topics (e.g. trade, inflation, AI)
  - agreements or programs if present (e.g. CUSMA)
- Use short noun phrases
- Avoid generic words like "news", "issue", "report"

------------------------
SUMMARY RULES:
- EXACTLY 60-65 words, one paragraph, 3-4 sentences max
- Start immediately with the main event (who/what/when if available)
- Include at least TWO specific data points (numbers, percentages, dates, or amounts) if present
- Prioritize information in this order:
  1. Core event (what happened)
  2. Key details (who, where, scale, numbers)
  3. Issue/failure/conflict (if any)
  4. Outcome, response, or current status
- Use neutral, factual North American journalism tone
- Short, direct, declarative sentences
- Attribute opinions clearly (e.g. "X said…")
- Use ONLY facts from the article — no assumptions, no outside knowledge

PROHIBITED in summary:
- No opinions, conclusions, or recommendations
- No added interpretation or inferred causes
- No filler phrases ("This article discusses", "The report highlights")
- No repetition

------------------------
QA_PASS RULES:
- false if: article is an ad, duplicate, promotional, or too thin (< 5 sentences of real content)
- true otherwise

------------------------
FINAL CHECK (MANDATORY):
1. Headline is under 12 words with a clear subject and action
2. Categories are from the allowed list only
3. Tags are specific and relevant
4. Summary is exactly 60-65 words
5. Output is valid JSON with no extra keys

Return ONLY valid JSON. No markdown fences, no extra text.

Original headline: {headline}
Article: {content}
"""


def process_article(headline: str, content: str) -> dict | None:
    """Call Ollama once and return parsed JSON, or None on failure."""
    prompt = PROMPT_TEMPLATE.format(
        headline=headline,
        content=content[:3000],
    )

    result = [None]
    error = [None]

    def call():
        try:
            resp = requests.post(
                f"{OLLAMA_HOST}/api/generate",
                json={
                    "model": MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.3},
                },
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "")
            result[0] = json.loads(raw)
        except Exception as e:
            error[0] = str(e)

    t = threading.Thread(target=call, daemon=True)
    t.start()
    t.join(timeout=TIMEOUT + 5)

    if t.is_alive():
        print("    [llm] timed out")
        return None
    if error[0]:
        print(f"    [llm] error: {error[0][:120]}")
        return None

    data = result[0]
    if not isinstance(data, dict):
        print("    [llm] unexpected response type")
        return None

    required = {"headline", "categories", "tags", "summary", "word_count", "qa_pass"}
    if not required.issubset(data):
        print(f"    [llm] missing keys: {required - data.keys()}")
        return None

    # Normalise: categories and tags must be lists
    if isinstance(data["categories"], str):
        data["categories"] = [data["categories"]]
    if isinstance(data["tags"], str):
        data["tags"] = [data["tags"]]

    return data


def is_ollama_running() -> bool:
    try:
        requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        return True
    except Exception:
        return False
