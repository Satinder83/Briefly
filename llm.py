import json
import os
import threading
import requests

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))

PROMPT_TEMPLATE = """\
You are a news editor. Given the article below, return a JSON object with exactly these keys:

{{
  "category": one of ["politics", "tech", "finance", "science", "world", "sports", "health"],
  "summary": "Use this prompt Role: Professional News Editor

Task: Summarize the article into a high-density, Inshorts-style brief.

STRICT RULES:

Headline:
- Write a short, factual, punchy headline (NOT included in word count).

Body:
- EXACTLY 60-65 words.
- ONE paragraph only.
- Maximum 3-4 sentences.

CONTENT RULES:
- Use ONLY facts from the article. No assumptions, no outside knowledge.
- Start immediately with the main event (who/what/when if available).
- Include at least TWO specific data points (numbers, percentages, dates, or amounts) if present in the article.
- Prioritize information in this order:
1. Core event (what happened)
2. Key details (who, where, scale, numbers)
3. Issue/failure/conflict (if any)
4. Outcome, response, or current status

STYLE RULES:
- Use neutral, factual North American journalism tone.
- Use short, direct, declarative sentences.
- Avoid vague terms like “surged,” “significant,” “experts say” unless backed by specific data or attribution.
- Do NOT generalize or summarize causes unless explicitly stated in the article.
- Attribute opinions or explanations clearly (e.g., “X said…”).

PROHIBITED:
- No opinions, conclusions, or recommendations.
- No added interpretation or inferred causes.
- No filler phrases (e.g., “This article discusses,” “The report highlights”).
- No repetition.

MANDATORY VALIDATION (before output):
1. Word count is between 60-65.
2. First sentence clearly states the main event.
3. At least two concrete facts (numbers/names) are included if available.
4. No information is added beyond the article.
5. Every sentence adds new information.

Output format:

Headline: <headline>

Summary: <60-65 word paragraph>",
  "word_count": integer count of words in the summary,
  "qa_pass": true if the article has enough substance to summarize, false if it is a duplicate, ad, or too short
}}

Return ONLY valid JSON, no markdown fences, no extra text.

Headline: {headline}
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

    required = {"category", "summary", "word_count", "qa_pass"}
    if not required.issubset(data):
        print(f"    [llm] missing keys: {required - data.keys()}")
        return None

    return data


def is_ollama_running() -> bool:
    try:
        requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        return True
    except Exception:
        return False
