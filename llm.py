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

SUMMARY TASK

Write a high-density news summary.

----------------------------------
OUTPUT REQUIREMENTS:
- EXACTLY 60-65 words
- ONE paragraph
- 3-4 sentences

----------------------------------
CONTENT RULES:
- Start immediately with the main event (who/what/when)
- Include AT LEAST TWO numeric facts from the article (dates, counts, percentages, amounts)
- Include at least ONE named person if present in the article
- Use only facts from the article (no assumptions, no outside knowledge)
- Use actual event status words (e.g., "evacuated", "closed", "fired", not "risk", "possible")

----------------------------------
PRIORITY ORDER:
1. Core event
2. Key details (who, where, numbers)
3. Conflict / issue
4. Outcome / current status

----------------------------------
STYLE:
- Neutral, factual North American journalism tone
- Short, direct sentences
- No filler phrases
- No repetition

----------------------------------
PROHIBITED:
- No opinions or conclusions
- No inferred causes not explicitly stated
- No vague language replacing concrete facts
- No hallucinated facts

----------------------------------
MANDATORY SELF-CHECK (BEFORE OUTPUT):

1. Word count = 60-65 exactly  
2. At least 2 numeric facts included  
3. Named person included (if present in article)  
4. No vague terms replacing real events  
5. No added or incorrect facts  
6. At least ONE related development/location/party beyond the lead event included

IF ANY RULE FAILS:
→ Rewrite the summary until ALL conditions are satisfied.

----------------------------------
OUTPUT:
Summary: <final 60-65 word paragraph only>

------------------------
QA_PASS RULES:
true if ALL of the following:
- Article has at least 5 sentences of real content
- Article is not an ad, duplicate, or promotional content
- Summary includes at least 2 numeric facts from the article
- Summary includes at least 1 named person (if article provides one)
- Summary uses actual event status words (not vague language)
- Summary contains no hallucinated facts

false if ANY of the following:
- Article is an ad, duplicate, promotional, or too thin (< 5 sentences)
- Summary omits a key number that was explicitly stated
- Summary omits a named person who was explicitly identified
- Summary uses vague language ("risk of", "impending") instead of actual status
- Summary contains a fact not present in the article

------------------------
FINAL CHECK (MANDATORY):
1. Headline is under 12 words with a clear subject and action
2. Categories are from the allowed list only
3. Tags are specific and relevant
4. Summary is exactly 60-65 words
5. Output is valid JSON with no extra keys
6. Summary includes at least 2 numeric facts from the article
7. Summary includes at least 1 named person (if present in article)
8. No hallucinated facts detected in summary

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
