"""
LangChain 1.x agent backed by Claude (LangGraph create_agent API).

Conversation history is persisted per session in data/history_{session_id}.json.
History is loaded before each call and saved after — no checkpointer needed.
"""
import json
from pathlib import Path
from typing import AsyncIterator

from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from agent.tools import (
    check_lakeshore_west_delays,
    get_oakville_station_info,
    get_next_service,
    get_service_exceptions,
)
from config import AGENT_ENABLED, ANTHROPIC_API_KEY, AGENT_MODEL

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

_TOOLS = [
    check_lakeshore_west_delays,
    get_oakville_station_info,
    get_next_service,
    get_service_exceptions,
]

_SYSTEM_PROMPT = """\
You are a helpful GO Transit commute assistant specialising in the Lakeshore West line.
You help commuters check real-time train delays, next departures, and station facilities.

You have access to live Metrolinx data via these tools:
- check_lakeshore_west_delays  → live delays for all Lakeshore West trains
- get_oakville_station_info    → Oakville GO facilities (elevator, parking, etc.)
- get_next_service             → next departures from any GO station (OA=Oakville, UN=Union)
- get_service_exceptions       → cancellations and service alerts

Always call the relevant tool before answering delay or schedule questions — never guess.
Be concise and practical. If the user mentions their usual train or stop, remember it.\
"""

_llm = None
_agent = None

if AGENT_ENABLED and ANTHROPIC_API_KEY:
    _llm = ChatAnthropic(model=AGENT_MODEL, api_key=ANTHROPIC_API_KEY, streaming=True)
    _agent = create_agent(_llm, tools=_TOOLS, system_prompt=_SYSTEM_PROMPT)


# ── JSON history helpers ───────────────────────────────────────────────────────

def _history_path(session_id: str) -> Path:
    return DATA_DIR / f"history_{session_id}.json"


def load_history(session_id: str) -> list[dict]:
    path = _history_path(session_id)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_history(session_id: str, history: list[dict]) -> None:
    _history_path(session_id).write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def clear_history(session_id: str) -> bool:
    path = _history_path(session_id)
    if path.exists():
        path.unlink()
        return True
    return False


def _build_messages(history: list[dict], new_message: str) -> list[BaseMessage]:
    """Convert stored history + new user message into LangChain message objects."""
    msgs: list[BaseMessage] = []
    for entry in history:
        if entry["role"] == "human":
            msgs.append(HumanMessage(content=entry["content"]))
        elif entry["role"] == "assistant":
            msgs.append(AIMessage(content=entry["content"]))
    msgs.append(HumanMessage(content=new_message))
    return msgs


def _extract_answer(result: dict) -> str:
    """Pull the final AI response text from the agent result dict."""
    messages = result.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            content = msg.content
            if isinstance(content, list):
                # Claude may return a list of content blocks
                parts = [
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in content
                    if not (isinstance(block, dict) and block.get("type") == "tool_use")
                ]
                text = "".join(parts).strip()
                if text:
                    return text
            elif isinstance(content, str) and content.strip():
                return content.strip()
    return ""


# ── Public streaming interface ─────────────────────────────────────────────────

async def chat_stream(message: str, session_id: str = "default") -> AsyncIterator[dict]:
    """
    Async generator yielding event dicts for SSE:
      {"type": "status", "text": "..."}   — tool being called
      {"type": "answer",  "text": "..."}  — final answer
      {"type": "error",   "text": "..."}  — on failure
    """
    if _agent is None:
        yield {
            "type": "answer",
            "text": (
                "The chat agent is currently disabled (AGENT_ENABLED=false). "
                "Set AGENT_ENABLED=true in .env and restart the server to re-enable it."
            ),
        }
        return

    history = load_history(session_id)
    messages = _build_messages(history, message)

    try:
        final_result: dict | None = None

        async for event in _agent.astream_events(
            {"messages": messages},
            version="v2",
        ):
            kind = event["event"]

            if kind == "on_tool_start":
                tool_name = event.get("name", "tool")
                friendly = {
                    "check_lakeshore_west_delays": "Checking live delays...",
                    "get_oakville_station_info": "Fetching Oakville GO station info...",
                    "get_next_service": "Fetching next departures...",
                    "get_service_exceptions": "Checking service alerts...",
                }.get(tool_name, f"Calling {tool_name}...")
                yield {"type": "status", "text": friendly}

            elif kind == "on_chain_end":
                data = event.get("data", {})
                output = data.get("output")
                if isinstance(output, dict) and "messages" in output:
                    final_result = output

        if final_result is not None:
            answer = _extract_answer(final_result)
        else:
            # Fallback: run without streaming to get the answer
            result = await _agent.ainvoke({"messages": messages})
            answer = _extract_answer(result)

        if not answer:
            answer = "I couldn't generate a response. Please try again."

        yield {"type": "answer", "text": answer}

        # Persist history
        save_history(session_id, history + [
            {"role": "human", "content": message},
            {"role": "assistant", "content": answer},
        ])

    except Exception as exc:
        yield {"type": "error", "text": f"Agent error: {exc}"}
