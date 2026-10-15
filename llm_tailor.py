import json
import re
import os
from openai import OpenAI
from prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from dotenv import load_dotenv

load_dotenv()


def get_client(api_key: str | None = None) -> OpenAI:
    key = api_key or os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        raise ValueError(
            "OpenRouter API key is required. "
            "Set OPENROUTER_API_KEY in .env or provide it in the app."
        )
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=key,
    )


FUSION_PANEL_MODELS = [
    "z-ai/glm-5.2",
    "anthropic/claude-sonnet-5",
    "qwen/qwen3.7-max",
]
FUSION_JUDGE_MODEL = "google/gemini-3.1-pro-preview"

# Cheap model used only to repair malformed JSON output so the expensive
# tailoring work is never thrown away over formatting noise.
REPAIR_MODEL = "deepseek/deepseek-chat"


def _is_fusion(model: str) -> bool:
    return model.lower().startswith("openrouter/fusion")


_CODE_FENCE_RE = re.compile(
    r"^\s*```(?:json|JSON)?\s*\n?(?P<body>.*?)```",
    re.DOTALL,
)
_REQUIRED_KEYS = ["name", "professional_summary", "skills", "experience"]


def _strip_code_fence(content: str) -> str:
    """Remove a single wrapping markdown code fence, if present."""
    m = _CODE_FENCE_RE.search(content)
    if m:
        return m.group("body").strip()
    return content.strip()


def _extract_balanced_json(content: str) -> str | None:
    """Return the first balanced top-level {...} object found, scanning braces."""
    start = content.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(content)):
        ch = content[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return content[start : i + 1]
    return None


def _repair_truncated_json(raw: str) -> str | None:
    """Best-effort fix for JSON truncated by a token limit: close open strings/arrays/objects."""
    candidate = _extract_balanced_json(raw)
    if candidate is None:
        # No balanced object — take from first '{' to end and try to close it.
        start = raw.find("{")
        if start == -1:
            return None
        candidate = raw[start:]
    # Count unclosed structural tokens (ignoring those inside strings).
    depth_obj = depth_arr = 0
    in_str = False
    esc = False
    for ch in candidate:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth_obj += 1
        elif ch == "}":
            depth_obj -= 1
        elif ch == "[":
            depth_arr += 1
        elif ch == "]":
            depth_arr -= 1
    suffix = ""
    if in_str:
        suffix += '"'
    suffix += "]" * max(depth_arr, 0) + "}" * max(depth_obj, 0)
    return candidate + suffix if suffix else candidate


def _extract_json(content: str) -> dict:
    """Multi-stage JSON extraction. Raises ValueError if nothing parses."""
    candidates: list[str] = []
    fenced = _strip_code_fence(content)
    candidates.append(fenced)
    balanced = _extract_balanced_json(fenced) or _extract_balanced_json(content)
    if balanced:
        candidates.append(balanced)

    seen: set[str] = set()
    for cand in candidates:
        if cand in seen:
            continue
        seen.add(cand)
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            repaired = _repair_truncated_json(cand)
            if repaired and repaired != cand:
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    pass
    raise ValueError("Could not extract JSON from model output.")


def _validate_cv(tailored_cv: dict) -> None:
    for key in _REQUIRED_KEYS:
        if key not in tailored_cv:
            raise ValueError(f"LLM response missing required key: {key}")


_REPAIR_PROMPT = """The following text was returned in response to a request for a JSON resume object, \
but it could not be parsed as valid JSON — it likely contains markdown code fences, commentary, \
or was truncated. Return ONLY a corrected, complete, valid JSON object with the same schema. \
Do not include any prose, code fences, or explanation.

Raw text:
"""


def _repair_with_model(client: OpenAI, raw: str) -> str:
    """Ask a cheap model to clean up the output so the expensive tailoring work is reused."""
    resp = client.chat.completions.create(
        model=REPAIR_MODEL,
        messages=[
            {
                "role": "user",
                "content": _REPAIR_PROMPT + raw[:8000],
            }
        ],
        temperature=0.0,
        max_tokens=10000,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content or ""


def tailor_resume(
    resume_text: str,
    job_description: str,
    api_key: str | None = None,
    model: str = "z-ai/glm-5.1",
    enforce_byok: bool = True,
    previous_cv: dict | None = None,
    feedback: str | None = None,
) -> dict:
    client = get_client(api_key)

    user_prompt = USER_PROMPT_TEMPLATE.format(
        resume_text=resume_text,
        job_description=job_description,
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    if previous_cv is not None and feedback:
        # Revision round: replay the earlier answer, then ask for a corrected version.
        messages.append({"role": "assistant", "content": json.dumps(previous_cv)})
        messages.append(
            {
                "role": "user",
                "content": (
                    "Revise the CV above based on this feedback. Keep everything the "
                    "feedback doesn't mention unchanged, and don't invent facts that "
                    "aren't in the original resume. Return the complete CV in the "
                    "same JSON format.\n\nFeedback:\n" + feedback
                ),
            }
        )

    extra_body = {
        "reasoning": {
            "effort": "xhigh",
        },
    }

    if _is_fusion(model):
        extra_body["plugins"] = [
            {
                "id": "fusion",
                "analysis_models": list(FUSION_PANEL_MODELS),
                "model": FUSION_JUDGE_MODEL,
            }
        ]
    elif enforce_byok and "gemini" in model.lower():
        extra_body["provider"] = {
            "only": ["Google AI Studio"]
        }

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.4,
        max_tokens=10000,
        response_format={"type": "json_object"},
        extra_body=extra_body,
    )

    content = response.choices[0].message.content or ""

    try:
        tailored_cv = _extract_json(content)
    except ValueError:
        # Fallback: have the model repair its own output rather than throwing away
        # the expensive tailoring work. Reuse the already-computed content.
        try:
            repaired = _repair_with_model(client, content)
            tailored_cv = _extract_json(repaired)
        except ValueError:
            raise ValueError(
                "LLM did not return valid JSON even after a repair pass. "
                "Raw response:\n" + content[:2000]
            )

    _validate_cv(tailored_cv)
    return tailored_cv