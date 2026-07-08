"""
AI Assistant API routes - Chat endpoint with SSE streaming.

The agent loop runs server-side. The frontend only sends chat text and
receives streamed events. Conversations are persisted to Supabase
(assistant_conversations / assistant_messages) with an in-memory LRU cache
in front. Write actions proposed by the model are held pending until the
user approves them via POST /assistant/actions/{action_id}.
"""

import json
from uuid import uuid4
from datetime import datetime, timezone
from collections import OrderedDict
from typing import Any, AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..config import get_settings
from ..services.supabase import get_supabase_admin
from ..services.assistant_tools import (
    TOOL_DEFINITIONS,
    ACTION_TOOL_DEFINITIONS,
    ACTION_TOOL_NAMES,
    run_tool,
    get_tool_summary,
    describe_action,
    execute_action,
)

router = APIRouter(prefix="/assistant", tags=["assistant"])
settings = get_settings()


# =============================================================================
# System Prompt
# =============================================================================

SYSTEM_PROMPT = """You are the PDM assistant for a small sheet-metal fabrication shop. You answer questions about parts, assemblies, BOMs, files, projects, manufacturing schedules, costs, and shop-floor status using the provided tools.

**Users:** Jack (CAD engineer), Dan (PM), Shop (shared account).

**Domain context:**
- Item numbers follow the format `abc####` (3 letters + 4-6 digits), always lowercase. Examples: `csp0030`, `wma20120`, `stp02810`.
- Prefixes: `mmc` = McMaster-Carr, `spn` = supplier part, `zzz` = reference/phantom.
- Lifecycle states: Design, Review, Released, Obsolete.
- File types: PDF (prints/drawings), STEP (3D CAD), DXF (flat patterns), SVG (bend drawings), CAD (native Creo files).

**Manufacturing (MRP) context:**
- MRP projects are shop jobs with a project code, customer, start date, and due date. Use `list_mrp_projects` for timelines/schedules and `get_mrp_project` for one job's detail and shop-floor progress.
- Costs: `get_project_cost_estimate` gives labor / material / outsourced / purchased totals plus overhead - the same numbers as the MRP cost page. `get_pricing_settings` shows labor rates, overhead multiplier, and per-material $/lb defaults. `list_raw_materials` shows stock prices and inventory; `list_low_stock_materials` shows what needs reordering.
- Routing: each manufactured item moves through workstations in sequence (`get_item_routing`).
- The work queue (`list_work_queue_tasks`) holds background file-generation tasks (DXF flat patterns, SVG bend drawings). If a user asks why a flat pattern is missing, check for failed tasks.
- `audit_project` runs a pre-flight check on a project (missing routing, prints, DXFs, prices, materials). Use it when asked if a job is ready.
- `get_time_analysis` compares estimated routing times to actual logged shop time.
- Treat cost estimates as estimates: mention that totals depend on current rates and material prices.

**Custom queries:**
For questions the purpose-built tools can't answer (cross-table aggregates, custom filters, counts), use `query_database` with a single SELECT. Prefer the purpose-built tools when they fit. Aggregate in SQL rather than pulling raw rows.

**Write actions (require approval):**
You can PROPOSE a few changes: re-queue a failed task, update a material price, change a routing time estimate, or change a cost setting. When you call one of these tools, it is NOT executed - the user sees an approval card and must click Approve. After proposing, briefly tell the user an approval card is waiting. NEVER claim a change was made until a later system note confirms it was approved and executed. If the user declines, don't re-propose the same action unless asked.

**BOM counting rule:**
When asked "how many X are in assembly Y", expand the BOM tree and calculate the total count by:
1. For each occurrence of the target part, multiply its quantity by all ancestor quantities.
2. Sum across all occurrences.
Show your math briefly so the user can verify.

**File delivery:**
When the user asks for a print, drawing, or file:
1. Call `list_item_files` (use `file_type: "PDF"` for prints/drawings).
2. Call `get_file_download_link` with the file ID.
3. Present the result as a markdown link: `[csp00200.pdf](url)`.
4. Mention the link expires in 1 hour.

**Grounding:**
Only state facts returned by your tools. If a tool returns no results or an error, say so honestly - never invent part data.

**Style:**
- Be concise and use plain language.
- Use markdown tables for BOM listings when appropriate.
- Item numbers should be shown in lowercase monospace: `csp00200`."""


# =============================================================================
# Session Storage (in-memory LRU cache in front of Supabase persistence)
# =============================================================================

class LRUCache(OrderedDict):
    """Simple LRU cache with max size."""

    def __init__(self, maxsize: int = 50):
        super().__init__()
        self.maxsize = maxsize

    def get(self, key, default=None):
        if key in self:
            self.move_to_end(key)
            return self[key]
        return default

    def set(self, key, value):
        if key in self:
            self.move_to_end(key)
        self[key] = value
        while len(self) > self.maxsize:
            self.popitem(last=False)


# conversation_id -> list of messages (API format, dicts only)
sessions: LRUCache = LRUCache(maxsize=50)

# action_id -> pending action proposal awaiting user approval
pending_actions: LRUCache = LRUCache(maxsize=100)

# Max messages sent to the model per request (history in DB is never trimmed)
MAX_MESSAGES_PER_CONVERSATION = 40


# =============================================================================
# Persistence helpers (best-effort: a DB hiccup never kills the chat)
# =============================================================================

def _ensure_conversation(conversation_id: str, title: Optional[str] = None,
                         page_context: Optional[str] = None) -> None:
    try:
        supabase = get_supabase_admin()
        existing = supabase.table("assistant_conversations").select("id").eq(
            "id", conversation_id
        ).maybe_single().execute()

        if existing and existing.data:
            update: dict[str, Any] = {
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            if page_context:
                update["page_context"] = page_context
            supabase.table("assistant_conversations").update(update).eq(
                "id", conversation_id
            ).execute()
        else:
            supabase.table("assistant_conversations").insert({
                "id": conversation_id,
                "title": (title or "")[:80] or None,
                "page_context": page_context,
            }).execute()
    except Exception as e:
        print(f"[Assistant] Warning: could not upsert conversation: {e}", flush=True)


def _save_message(conversation_id: str, role: str, content: Any,
                  hidden: bool = False) -> None:
    try:
        supabase = get_supabase_admin()
        supabase.table("assistant_messages").insert({
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "hidden": hidden,
        }).execute()
    except Exception as e:
        print(f"[Assistant] Warning: could not persist message: {e}", flush=True)


def _load_history(conversation_id: str) -> list[dict]:
    """Load full message history from DB in Anthropic API format."""
    try:
        supabase = get_supabase_admin()
        result = supabase.table("assistant_messages").select(
            "role, content"
        ).eq("conversation_id", conversation_id).order("created_at").execute()
        return [
            {"role": m["role"], "content": m["content"]}
            for m in (result.data or [])
        ]
    except Exception as e:
        print(f"[Assistant] Warning: could not load history: {e}", flush=True)
        return []


def _get_page_context(conversation_id: str) -> Optional[str]:
    try:
        supabase = get_supabase_admin()
        result = supabase.table("assistant_conversations").select(
            "page_context"
        ).eq("id", conversation_id).maybe_single().execute()
        if result and result.data:
            return result.data.get("page_context")
    except Exception:
        pass
    return None


def _get_history(conversation_id: str) -> list[dict]:
    """Get history from cache, falling back to DB (survives restarts)."""
    history = sessions.get(conversation_id)
    if history is None:
        history = _load_history(conversation_id)
        sessions.set(conversation_id, history)
    return history


# =============================================================================
# History shaping for the API call
# =============================================================================

def _content_to_blocks(content: Any) -> list[dict]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return list(content)


def _merge_consecutive(messages: list[dict]) -> list[dict]:
    """Merge consecutive same-role messages (API requires alternating roles).

    tool_result blocks are kept ahead of text blocks within a merged message,
    as the API requires.
    """
    merged: list[dict] = []
    for msg in messages:
        if merged and merged[-1]["role"] == msg["role"]:
            blocks = _content_to_blocks(merged[-1]["content"]) + _content_to_blocks(msg["content"])
            tool_results = [b for b in blocks if b.get("type") == "tool_result"]
            others = [b for b in blocks if b.get("type") != "tool_result"]
            merged[-1] = {"role": msg["role"], "content": tool_results + others}
        else:
            merged.append(msg)
    return merged


def _trim_for_api(history: list[dict]) -> list[dict]:
    """Trim to the last N messages without splitting a tool_use/tool_result pair.

    The window must start at a plain user text message so the model never sees
    an orphaned tool_result.
    """
    if len(history) <= MAX_MESSAGES_PER_CONVERSATION:
        return _merge_consecutive(history)

    window = history[-MAX_MESSAGES_PER_CONVERSATION:]
    start = 0
    for i, msg in enumerate(window):
        if msg["role"] == "user" and isinstance(msg["content"], str):
            start = i
            break
    return _merge_consecutive(window[start:])


# =============================================================================
# Request/Response Models
# =============================================================================

class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str
    context: str | None = None  # e.g. "Viewing MRP project WM2121"


class ActionDecision(BaseModel):
    approve: bool


# =============================================================================
# SSE Event Helpers
# =============================================================================

def sse_event(event: str, data: dict) -> str:
    """Format an SSE event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# =============================================================================
# Chat Endpoint
# =============================================================================

@router.post("/chat")
async def chat(request: ChatRequest):
    """
    Chat with the AI assistant.

    Returns a Server-Sent Events stream with:
    - start: {conversation_id}
    - text: {delta} - incremental text
    - tool: {name, summary} - tool execution status
    - action: {action_id, name, description, params} - proposed write action awaiting approval
    - done: {} - turn complete
    - error: {message} - fatal error
    """
    # Check API key
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=503,
            detail="AI assistant is not configured (missing ANTHROPIC_API_KEY)"
        )

    # Get or create conversation
    is_new = request.conversation_id is None
    conversation_id = request.conversation_id or uuid4().hex
    history = [] if is_new else _get_history(conversation_id)

    _ensure_conversation(
        conversation_id,
        title=request.message if is_new or not history else None,
        page_context=request.context,
    )

    # Add user message
    history.append({
        "role": "user",
        "content": request.message
    })
    sessions.set(conversation_id, history)
    _save_message(conversation_id, "user", request.message)

    page_context = request.context or _get_page_context(conversation_id)

    async def generate() -> AsyncGenerator[str, None]:
        """SSE event generator with agent loop."""
        import anthropic

        print(f"[Assistant] Starting chat for conversation {conversation_id}", flush=True)
        yield sse_event("start", {"conversation_id": conversation_id})

        try:
            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

            system_blocks = [{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"}
            }]
            if page_context:
                system_blocks.append({
                    "type": "text",
                    "text": f"Current page context: {page_context}"
                })

            loop_count = 0
            max_loops = 8

            nonlocal history

            while loop_count < max_loops:
                loop_count += 1

                accumulated_text = ""
                response_blocks = []
                stop_reason = None

                print(f"[Assistant] Loop {loop_count}: calling Anthropic API...", flush=True)
                async with client.messages.stream(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=4096,
                    system=system_blocks,
                    tools=TOOL_DEFINITIONS + ACTION_TOOL_DEFINITIONS,
                    messages=_trim_for_api(history),
                ) as stream:
                    async for event in stream:
                        if event.type == "content_block_delta":
                            if hasattr(event.delta, "text"):
                                yield sse_event("text", {"delta": event.delta.text})
                                accumulated_text += event.delta.text

                    # Get final message
                    response = await stream.get_final_message()
                    response_blocks = [
                        block.model_dump(exclude_none=True)
                        for block in response.content
                    ]
                    stop_reason = response.stop_reason

                    # Log usage for monitoring
                    if response.usage:
                        print(f"[Assistant] Usage: input={response.usage.input_tokens}, "
                              f"output={response.usage.output_tokens}, "
                              f"cache_read={getattr(response.usage, 'cache_read_input_tokens', 0)}")

                # Add assistant response to history
                history.append({
                    "role": "assistant",
                    "content": response_blocks
                })
                sessions.set(conversation_id, history)
                _save_message(conversation_id, "assistant", response_blocks)

                # If not a tool use, we're done
                if stop_reason != "tool_use":
                    break

                # Execute tools (write actions are held for approval instead)
                tool_results = []
                for block in response_blocks:
                    if block.get("type") != "tool_use":
                        continue

                    name = block["name"]
                    arguments = block.get("input") or {}

                    if name in ACTION_TOOL_NAMES:
                        # Propose, don't execute
                        action_id = uuid4().hex
                        description = describe_action(name, arguments)
                        pending_actions.set(action_id, {
                            "name": name,
                            "arguments": arguments,
                            "description": description,
                            "conversation_id": conversation_id,
                        })
                        yield sse_event("action", {
                            "action_id": action_id,
                            "name": name,
                            "description": description,
                            "params": arguments,
                        })
                        result = {
                            "status": "pending_approval",
                            "note": (
                                "This action was NOT executed. An approval card was shown "
                                "to the user. Tell them it is waiting for their approval. "
                                "A system note will confirm the outcome later."
                            )
                        }
                    else:
                        summary = get_tool_summary(name, arguments)
                        yield sse_event("tool", {"name": name, "summary": summary})
                        result = run_tool(name, arguments)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": json.dumps(result)
                    })

                # Add all tool results in a single user message
                history.append({
                    "role": "user",
                    "content": tool_results
                })
                sessions.set(conversation_id, history)
                _save_message(conversation_id, "user", tool_results, hidden=True)

            if loop_count >= max_loops:
                yield sse_event("error", {"message": "Too many tool calls - please simplify your question"})
            else:
                yield sse_event("done", {})

        except anthropic.APIError as e:
            yield sse_event("error", {"message": f"API error: {str(e)}"})
        except Exception as e:
            print(f"[Assistant] Error: {e}")
            yield sse_event("error", {"message": f"Internal error: {str(e)}"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


# =============================================================================
# Action Approval Endpoint
# =============================================================================

@router.post("/actions/{action_id}")
async def respond_to_action(action_id: str, decision: ActionDecision):
    """Approve or decline a proposed write action. Approval executes it."""
    action = pending_actions.get(action_id)
    if action is None:
        raise HTTPException(
            status_code=404,
            detail="Action not found or expired (actions must be approved in the same server session)"
        )
    del pending_actions[action_id]

    if decision.approve:
        result = execute_action(action["name"], action["arguments"])
        outcome = "APPROVED and executed"
    else:
        result = {"status": "declined"}
        outcome = "DECLINED"

    # Record the outcome so the model sees it on the next turn
    conversation_id = action["conversation_id"]
    note = (
        f"[System note: the user {outcome} the proposed action "
        f"\"{action['description']}\". Result: {json.dumps(result)}]"
    )
    history = _get_history(conversation_id)
    history.append({"role": "user", "content": note})
    sessions.set(conversation_id, history)
    _save_message(conversation_id, "user", note, hidden=True)

    return {
        "action_id": action_id,
        "approved": decision.approve,
        "description": action["description"],
        "result": result,
    }


# =============================================================================
# Conversation Endpoints
# =============================================================================

@router.get("/conversations")
async def list_conversations():
    """List recent conversations (newest first)."""
    try:
        supabase = get_supabase_admin()
        result = supabase.table("assistant_conversations").select(
            "id, title, updated_at"
        ).order("updated_at", desc=True).limit(20).execute()
        return {"conversations": result.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not list conversations: {e}")


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: str):
    """Get displayable messages for a conversation (tool internals hidden)."""
    try:
        supabase = get_supabase_admin()
        result = supabase.table("assistant_messages").select(
            "role, content, created_at"
        ).eq("conversation_id", conversation_id).eq(
            "hidden", False
        ).order("created_at").execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load conversation: {e}")

    messages = []
    for m in result.data or []:
        content = m["content"]
        if isinstance(content, str):
            text = content
        else:
            text = "\n\n".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ).strip()
        if text:
            messages.append({
                "role": m["role"],
                "content": text,
                "created_at": m["created_at"],
            })

    return {"conversation_id": conversation_id, "messages": messages}


@router.delete("/chat/{conversation_id}")
async def clear_conversation(conversation_id: str):
    """Delete a conversation from memory and the database."""
    if conversation_id in sessions:
        del sessions[conversation_id]
    try:
        supabase = get_supabase_admin()
        supabase.table("assistant_conversations").delete().eq(
            "id", conversation_id
        ).execute()
    except Exception as e:
        print(f"[Assistant] Warning: could not delete conversation: {e}", flush=True)
    return {"message": "Conversation cleared"}
