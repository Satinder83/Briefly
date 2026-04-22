import json
import os
import re
import threading
import requests

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")

ALLOWED_CATEGORIES = [
    "politics", "policy", "elections", "law", "economy", "markets", "banking",
    "business", "corporate", "technology", "ai", "cybersecurity", "health",
    "science", "environment", "world", "diplomacy", "defense", "energy",
    "society", "education", "immigration", "sports",
]

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SUMMARY_PROMPT = """\
Role: News Editor

Write a summary of the article below.

RULES:
- Between 60-65 words
- ONE paragraph, 3-4 sentences
- Start with the main event (who/what/when)
- Include at least TWO numeric facts (numbers, dates, percentages, amounts) if available.
- Include at least ONE named person if present in the article
- Use only facts from the article — no assumptions, no outside knowledge
- Use numbers from the article - no assumptions, no outisde knowledge
- Neutral, factual North American journalism tone
- No filler phrases, no opinions, no repetition

PROHIBITED:
- Converting vague quantities ("dozens", "several", "many") into specific numbers not in the article
- Inferring scale, impact, or affected populations not stated in the article
- Adding recommendations or prescriptive language ("advises", "should", "must")
- Changing event status words to softer alternatives ("risk of" vs actual status)

MANDATORY CHECK:
At least ONE related development, location, or additional party beyond the lead event included

CRITICAL FAILURE MODE:
- Adding real-world knowledge about companies, products, or markets = automatic failure
- Adding any fact not explicitly stated in the article = automatic failure
- Only use facts that appear in the article text
- If the article does not mention a statistic, do not include it

OUTPUT format (exactly):
Summary: <text>

Article:
{content}
"""

ENRICH_PROMPT = """\
Return a JSON object with exactly these keys:

{{
  "headline": "<rewritten headline>",
  "categories": ["<primary>"],
  "tags": ["<tag1>", "<tag2>", "<tag3>"]
}}

RULES:
- Headline: max 12 words, WHO + WHAT, strong present-tense verb, AP style, no clickbait
- Categories: 1-3, choose ONLY from this list: {categories}
- Tags: 3-6, key people/orgs/countries/topics, short noun phrases, no generic words

Article:
{content}

Return ONLY valid JSON. No markdown, no extra text.
"""

FIX_PROMPT = """\
Fix the summary below to address the listed issues.

Issues:
{issues}

CRITICAL — Before rewriting, check:
- Do NOT add any statistic, number, or figure not in the original article
- Do NOT add real-world knowledge (company size, market data, user counts)
- Do NOT infer capabilities or outcomes not stated
- Every fact in the summary must appear verbatim or be paraphrased from the article

Requirements:
- Between 60-65 words
- Include at least 2 numeric facts FROM THE ARTICLE ONLY
- Include a named person if one appears in the article
- Use only facts from the article — no incorrect or added facts
- Neutral journalism tone
- Do not convert vague article phrases ("dozens", "several") into specific numbers
- Do not infer scale or impact not present in article
- Do not add recommendations or interpretation

Summary:
{summary}

Return ONLY the rewritten summary text. No labels, no JSON.
"""

REVIEW_PROMPT = """\
Role: Senior News Editor

Score the summary against the article.

SCORING:
- Accuracy (0-20): Are all facts correct and sourced from the article? Any invented statistics (user counts, market size) not in article = 0 accuracy points.
- Coverage (0-10): Are the most important facts included?
- Density (0-10): Is every sentence informative with no filler?
- Clarity (0-5): Is it easy to read and understand?
- Style (0-5): Does it follow AP/Reuters neutral journalism tone?

HALLUCINATION CHECK — Flag these as accuracy issues:
- Invented statistics (user counts, market figures, percentages)
- Numbers not in the article
- Scale/impact claims not present

RULES:
- Use only the article as source of truth
- Be strict
- No long explanations

Return JSON:
{{
  "score": <total 0-50>,
  "accuracy": <0-20>,
  "coverage": <0-10>,
  "density": <0-10>,
  "clarity": <0-5>,
  "style": <0-5>,
  "verdict": "Excellent|Good|Needs Improvement|Poor",
  "issues": ["<issue1>", "<issue2>"]
}}

Article:
{content}

Summary:
{summary}
"""

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def word_count(text: str) -> int:
    return len(text.split())

def has_numbers(text: str) -> bool:
    return len(re.findall(r'\d+', text)) >= 2

def has_name(text: str) -> bool:
    # Check for common name patterns (first + last capitalized)
    pattern = r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b'
    return bool(re.search(pattern, text))

def validate(summary: str, require_word_count: bool = True) -> dict:
    return {
        "word_ok":    require_word_count and (60 <= word_count(summary) <= 65),
        "numbers_ok": has_numbers(summary),
        "name_ok":    has_name(summary),
    }

# ---------------------------------------------------------------------------
# LLM callers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> str:
    """Strip markdown fences and extract the first JSON object from text."""
    text = text.strip()
    # Strip ```json ... ``` or ``` ... ``` fences
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    text = text.strip()
    # Find first complete { ... } block
    match = re.search(r'\{[\s\S]*\}', text)
    return match.group(0) if match else text


def _call(prompt: str, use_json: bool, temperature: float) -> str | None:
    result = [None]
    error = [None]

    def run():
        try:
            body = {
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature},
            }
            # format="json" helps local models but cloud models may ignore/reject it
            # Only set it for non-cloud models
            if use_json and not MODEL.endswith(":cloud"):
                body["format"] = "json"
            headers = {"Authorization": f"Bearer {OLLAMA_API_KEY}"} if OLLAMA_API_KEY else {}
            resp = requests.post(f"{OLLAMA_HOST}/api/generate", json=body, headers=headers, timeout=TIMEOUT)
            resp.raise_for_status()
            result[0] = resp.json().get("response", "").strip()
        except Exception as e:
            error[0] = str(e)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=TIMEOUT + 5)

    if t.is_alive():
        print("    [llm] timed out")
        return None
    if error[0]:
        print(f"    [llm] error: {error[0][:120]}")
        return None
    return result[0]

def call_llm(prompt: str) -> str:
    return _call(prompt, use_json=False, temperature=0.3) or ""

def call_llm_json(prompt: str, temperature: float = 0.3) -> str:
    raw = _call(prompt, use_json=True, temperature=temperature) or ""
    return _extract_json(raw) if raw else ""

# ---------------------------------------------------------------------------
# Reviewer
# ---------------------------------------------------------------------------

def run_reviewer(content: str, summary: str) -> dict | None:
    raw = call_llm_json(REVIEW_PROMPT.format(content=content[:3000], summary=summary), temperature=0.1)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception as e:
        print(f"    [reviewer] parse error: {e}")
        return None

# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def process_article(headline: str, content: str) -> dict | None:

    # Check for thin articles - skip 60-65 word requirement
    article_words = len(content.split())
    allow_short = article_words < 100


    # STEP 1 — generate summary
    summary_raw = call_llm(SUMMARY_PROMPT.format(content=content[:3000]))
    if not summary_raw:
        print("    [llm] summary generation failed")
        return None
    summary = summary_raw.replace("Summary:", "").strip()



    # STEP 2 — validate + retry (max 2 attempts)
    val = validate(summary, require_word_count=not allow_short)
    
    retries = 0
    while retries < 2:
        issues = []
        if not allow_short and not val["word_ok"]:
            issues.append(f"Fix word count to 60-65 (currently {word_count(summary)})")
        if not val["numbers_ok"]:
            issues.append("Add at least 2 numeric facts")
        if not val["name_ok"]:
            issues.append("Include a named person if one appears in the article")
        
        if not issues:
            break  # All checks passed
        
        print(f"    [validate] retry {retries + 1} — issues: {issues}")
        fixed = call_llm(FIX_PROMPT.format(summary=summary, issues="\n".join(f"- {i}" for i in issues)))
        if fixed:
            summary = fixed.replace("Summary:", "").strip()
        val = validate(summary)
        retries += 1

    # # STEP 2 — validate + retry (max 2 attempts)
    # val = validate(summary)
    # retries = 0
    # while not all(val.values()) and retries < 2:
    #     issues = []
    #     if not val["word_ok"]:
    #         issues.append(f"Fix word count to 60-65 (currently {word_count(summary)})")
    #     if not val["numbers_ok"]:
    #         issues.append("Add at least 2 numeric facts")
    #     if not val["name_ok"]:
    #         issues.append("Include a named person if one appears in the article")
    #     print(f"    [validate] retry {retries + 1} — issues: {issues}")
    #     fixed = call_llm(FIX_PROMPT.format(summary=summary, issues="\n".join(f"- {i}" for i in issues)))
    #     if fixed:
    #         summary = fixed.replace("Summary:", "").strip()
    #     val = validate(summary)
    #     retries += 1

    # STEP 3 — headline + categories + tags
    enrich_raw = call_llm_json(ENRICH_PROMPT.format(
        content=content[:3000],
        categories=", ".join(ALLOWED_CATEGORIES),
    ))
    try:
        enrich = json.loads(enrich_raw)
    except Exception:
        enrich = {}

    if isinstance(enrich.get("categories"), str):
        enrich["categories"] = [enrich["categories"]]
    if isinstance(enrich.get("tags"), str):
        enrich["tags"] = [enrich["tags"]]

    # STEP 4 — reviewer
    print("    [reviewer] scoring …")
    review = run_reviewer(content, summary)
    review_score = 0
    review_verdict = ""
    review_issues = []

    if review and isinstance(review, dict):
        review_score = review.get("score", 0)
        review_verdict = review.get("verdict", "")
        review_issues = review.get("issues", [])
        print(f"    [reviewer] score={review_score}/50 verdict={review_verdict}")

    # STEP 5 — auto-fix if reviewer score is low
    if review_score < 45:
        print(f"    [reviewer] low score ({review_score}/50), retrying fix …")
        issues_text = "\n".join(
            f"- {i}" for i in (review_issues or ["Improve factual accuracy and completeness"])
        )
        fixed = call_llm(FIX_PROMPT.format(summary=summary, issues=issues_text))
        if fixed:
            summary = fixed.replace("Summary:", "").strip()
            val = validate(summary)
            review2 = run_reviewer(content, summary)
            if review2 and isinstance(review2, dict):
                review_score = review2.get("score", review_score)
                review_verdict = review2.get("verdict", review_verdict)
                review_issues = review2.get("issues", review_issues)
                print(f"    [reviewer] post-fix score={review_score}/50 verdict={review_verdict}")

    
    return {
        "headline":       enrich.get("headline") or headline,
        "categories":     enrich.get("categories") or ["world"],
        "tags":           enrich.get("tags") or [],
        "summary":        summary,
        "word_count":     word_count(summary),
        "qa_pass":        all(val.values()) or allow_short,  # Allow short articles
        "article_words":  article_words,  # Debug info
        "review_score":   review_score,
        "review_verdict": review_verdict,
        "review_issues":  review_issues,
    }
    
    


def is_ollama_running() -> bool:
    try:
        headers = {"Authorization": f"Bearer {OLLAMA_API_KEY}"} if OLLAMA_API_KEY else {}
        requests.get(f"{OLLAMA_HOST}/api/tags", headers=headers, timeout=5)
        return True
    except Exception:
        return False
