#!/usr/bin/env python3
"""Streamlit demo chat for agentic NDAP metadata search."""

from __future__ import annotations

import html
import json
import re
from typing import Any

import httpx
import streamlit as st

import query

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-5.5"


def _json_from_text(text: str) -> dict[str, Any]:
    """Extract a small JSON object from a model response."""

    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def call_openrouter(
    *,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/artvandelay/ndap-deep-research-agent",
        "X-Title": "NDAP Deep Research Agent Demo",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    with httpx.Client(timeout=90.0) as client:
        response = client.post(OPENROUTER_CHAT_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    return data["choices"][0]["message"]["content"]


def plan_search(question: str, api_key: str, model: str) -> dict[str, str]:
    system = (
        "You plan searches over a local NDAP metadata index. Return JSON only. "
        "Choose a concise FTS-style search_query of important nouns and synonyms. "
        "Do not answer the user's question."
    )
    user = (
        "Question:\n"
        f"{question}\n\n"
        'Return exactly: {"search_query": "...", "reason": "..."}'
    )
    try:
        content = call_openrouter(
            api_key=api_key,
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.0,
        )
        parsed = _json_from_text(content)
        search_query = str(parsed.get("search_query") or question).strip()
        reason = str(parsed.get("reason") or "Model-derived search terms.").strip()
        return {"search_query": search_query, "reason": reason}
    except Exception as exc:
        return {
            "search_query": question,
            "reason": f"Planner fallback used because OpenRouter planning failed: {exc}",
        }


def safe_search(search_text: str, limit: int = 8) -> tuple[str, list[dict[str, Any]]]:
    """Run FTS search, falling back to simple alphanumeric terms if needed."""

    try:
        return search_text, query.search_datasets(search_text, limit=limit)
    except Exception:
        safe = " ".join(re.findall(r"[A-Za-z0-9]+", search_text))
        if not safe:
            safe = search_text
        return safe, query.search_datasets(safe, limit=limit)


def candidate_metadata(dataset_id: int) -> dict[str, Any]:
    metadata = query.get_dataset_metadata(dataset_id)
    dataset = metadata["dataset"]
    indicators = [
        item["display_name"]
        for item in metadata["indicators"][:10]
        if item.get("display_name")
    ]
    dimensions = [
        item["display_name"]
        for item in metadata["dimensions"][:10]
        if item.get("display_name")
    ]
    return {
        "dataset_id": dataset["dataset_id"],
        "name": dataset["name"],
        "description": dataset.get("description", ""),
        "sector": dataset.get("sector", ""),
        "ministry": dataset.get("ministry", ""),
        "years": f"{dataset.get('from_year') or '?'}-{dataset.get('to_year') or '?'}",
        "geo_levels": dataset.get("geo_levels", ""),
        "n_indicators": dataset.get("n_indicators", 0),
        "n_dimensions": dataset.get("n_dimensions", 0),
        "sample_indicators": indicators,
        "sample_dimensions": dimensions,
    }


def synthesize_answer(
    *,
    question: str,
    candidates: list[dict[str, Any]],
    api_key: str,
    model: str,
) -> str:
    system = (
        "You are an NDAP-only research assistant. Answer using only the supplied "
        "local NDAP metadata search results. Do not invent raw values, causal claims, "
        "or future predictions. If raw data is needed, say which dataset should be "
        "downloaded next. Always cite dataset IDs."
    )
    user = (
        "User question:\n"
        f"{question}\n\n"
        "Retrieved NDAP candidate metadata:\n"
        f"{json.dumps(candidates, indent=2)}\n\n"
        "Give a concise answer with: likely dataset(s), why they match, and next action."
    )
    return call_openrouter(
        api_key=api_key,
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.2,
    )


def tool_line(name: str, detail: str, duration: str = "local") -> str:
    return (
        '<div class="tool-line">'
        f'<span class="dot"></span><span class="tool-name">{html.escape(name)}</span>'
        f'<span class="tool-detail">{html.escape(detail)}</span>'
        f'<span class="duration">{html.escape(duration)}</span>'
        "</div>"
    )


def render_trace(trace: list[tuple[str, str, str]]) -> None:
    lines = [tool_line(name, detail, duration) for name, detail, duration in trace]
    st.markdown('<div class="agent-shell">' + "\n".join(lines) + "</div>", unsafe_allow_html=True)


def apply_style() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: radial-gradient(circle at top left, #1b2430 0, #0b0f14 38%, #05070a 100%);
            color: #e6edf3;
        }
        [data-testid="stSidebar"] {
            background: #090d12;
            border-right: 1px solid #263241;
        }
        .hero {
            border: 1px solid #273445;
            border-radius: 18px;
            padding: 20px 22px;
            background: linear-gradient(135deg, rgba(31, 42, 58, 0.95), rgba(9, 13, 18, 0.95));
            box-shadow: 0 14px 45px rgba(0,0,0,0.35);
            margin-bottom: 16px;
        }
        .hero h1 {
            margin: 0;
            font-size: 1.8rem;
            letter-spacing: -0.02em;
        }
        .hero p {
            color: #9fb2c8;
            margin: 8px 0 0 0;
        }
        .agent-shell {
            border: 1px solid #253244;
            border-radius: 14px;
            padding: 12px 14px;
            background: rgba(3, 7, 12, 0.92);
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
            margin: 10px 0 18px 0;
        }
        .tool-line {
            display: flex;
            gap: 10px;
            align-items: baseline;
            padding: 5px 0;
            border-bottom: 1px solid rgba(255,255,255,0.04);
        }
        .tool-line:last-child {
            border-bottom: 0;
        }
        .dot {
            width: 9px;
            height: 9px;
            border-radius: 999px;
            background: #f7c948;
            box-shadow: 0 0 12px rgba(247,201,72,0.75);
            flex: 0 0 9px;
        }
        .tool-name {
            color: #f8d66d;
            font-weight: 700;
            min-width: 190px;
        }
        .tool-detail {
            color: #c8d4e3;
            flex: 1;
        }
        .duration {
            color: #7f8fa3;
            font-size: 0.82rem;
        }
        .candidate-card {
            border: 1px solid #263241;
            border-radius: 12px;
            padding: 12px;
            background: rgba(13, 19, 27, 0.82);
            margin-bottom: 8px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="NDAP Agent Demo", page_icon="◼", layout="wide")
    apply_style()

    st.markdown(
        """
        <div class="hero">
            <h1>NDAP Deep Research Agent</h1>
            <p>Hermes-inspired chat demo over a local SQLite metadata index. The model plans a search, tools retrieve NDAP datasets, and the answer stays grounded in retrieved metadata.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.subheader("OpenRouter")
        api_key = st.text_input("API key", type="password", placeholder="sk-or-...")
        model = st.text_input("Model", value=DEFAULT_MODEL, help="Any OpenRouter model slug")
        result_limit = st.slider("Candidate datasets", min_value=3, max_value=12, value=8)
        st.caption("Your API key is used only for this browser session and is not written to disk.")

    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": (
                    "Ask an NDAP question like: `Which datasets cover slum population by city?` "
                    "or `Find education datasets with district-level enrolment by social category.`"
                ),
            }
        ]

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    question = st.chat_input("Ask an NDAP dataset discovery question...")
    if not question:
        return

    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    if not api_key.strip() or not model.strip():
        warning = "Enter an OpenRouter API key and model name in the sidebar to run the demo agent."
        st.session_state.messages.append({"role": "assistant", "content": warning})
        with st.chat_message("assistant"):
            st.warning(warning)
        return

    with st.chat_message("assistant"):
        trace: list[tuple[str, str, str]] = []
        with st.spinner("Planning NDAP search..."):
            plan = plan_search(question, api_key.strip(), model.strip())
        trace.append(("Plan Search", plan["reason"], "model"))

        with st.spinner("Searching local metadata index..."):
            executed_query, matches = safe_search(plan["search_query"], limit=result_limit)
        trace.append(("search_datasets", f'q="{executed_query}" -> {len(matches)} candidates', "SQLite FTS5"))

        candidates: list[dict[str, Any]] = []
        for match in matches[: min(5, len(matches))]:
            dataset_id = int(match["id"])
            candidates.append(candidate_metadata(dataset_id))
        trace.append(("get_dataset_metadata", f"{len(candidates)} candidate metadata payloads", "SQLite"))

        render_trace(trace)

        if not candidates:
            answer = "I could not find matching NDAP datasets in the local index. Try a broader query."
            st.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})
            return

        with st.expander("Retrieved candidate datasets", expanded=True):
            for candidate in candidates:
                st.markdown(
                    f"""
                    <div class="candidate-card">
                    <b>{candidate['dataset_id']} | {html.escape(candidate['name'])}</b><br/>
                    <span>{html.escape(candidate.get('description') or 'No description')}</span><br/>
                    <small>{html.escape(candidate.get('sector') or '')} · {html.escape(candidate.get('ministry') or '')} · {html.escape(candidate.get('years') or '')}</small>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        with st.spinner("Synthesizing grounded answer..."):
            try:
                answer = synthesize_answer(
                    question=question,
                    candidates=candidates,
                    api_key=api_key.strip(),
                    model=model.strip(),
                )
            except Exception as exc:
                ids = ", ".join(str(candidate["dataset_id"]) for candidate in candidates)
                answer = (
                    "The local search completed, but the model synthesis call failed. "
                    f"Candidate dataset IDs: {ids}. Error: `{exc}`"
                )
        st.markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()
