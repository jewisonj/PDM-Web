"""
AI Assistant API routes - Chat endpoint with SSE streaming.

The agent loop runs server-side. The frontend only sends chat text and
receives streamed events. Conversation state is kept in-memory.
"""

import json
import asyncio
from uuid import uuid4
from collections import OrderedDict
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..config import get_settings
from ..services.assistant_tools import (
    TOOL_DEFINITIONS,
    run_tool,
    get_tool_summary,
)

router = APIRouter(prefix="/assistant", tags=["assistant"])
settings = get_settings()


# =============================================================================
# System Prompt
# =============================================================================

SYSTEM_PROMPT = """You are the PDM assistant for a small sheet-metal fabrication shop. You answer questions about parts, assemblies, BOMs, files, projects, manufacturing schedules, costs, and shop-floor status using the provided tools. All tools are read-only - you can look things up but never change data.

**Users:** Jack (CAD engineer), Dan (PM), Shop (shared account).

**Domain context:**
- Item numbers follow the format `abc####` (3 letters + 4-6 digits), always lowercase. Examples: `csp0030`, `wma20120`, `stp02810`.
- Prefixes: `mmc` = McMaster-Carr, `spn` = supplier part, `zzz` = reference/phantom.
- Lifecycle states: Design, Review, Released, Obsolete.
- File types: PDF (prints/drawings), STEP (3D CAD), DXF (flat patterns), SVG (bend drawings), CAD (native Creo files).

**Manufacturing (MRP) context:**
- MRP projects are shop jobs with a project code, customer, start date, and due date. Use `list_mrp_projects` for timelines/schedules and `get_mrp_project` for one job's detail and shop-floor progress.
- Costs: `get_project_cost_estimate` gives labor / material / outsourced / purchased totals plus overhead - the same numbers as the MRP cost page. `get_pricing_settings` shows labor rates, overhead multiplier, and per-material $/lb defaults. `list_raw_materials` shows stock prices and inventory.
- Routing: each manufactured item moves through workstations in sequence (`get_item_routing`).
- The work queue (`list_work_queue_tasks`) holds background file-generation tasks (DXF flat patterns, SVG bend drawings). If a user asks why a flat pattern is missing, check for failed tasks.
- Treat cost estimates as estimates: mention that totals depend on current rates and material prices.

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
# Session Storage (in-memory, single server)
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


# conversation_id -> list of messages
sessions: LRUCache = LRUCache(maxsize=50)

# Max messages per conversation (to prevent runaway context)
MAX_MESSAGES_PER_CONVERSATION = 40


# =============================================================================
# Request/Response Models
# =============================================================================

class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str


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
    conversation_id = request.conversation_id or uuid4().hex
    history = sessions.get(conversation_id, [])

    # Add user message
    history.append({
        "role": "user",
        "content": request.message
    })

    # Trim history if too long (keep system context fresh)
    if len(history) > MAX_MESSAGES_PER_CONVERSATION:
        # Keep first message and last N-1 messages
        history = history[:1] + history[-(MAX_MESSAGES_PER_CONVERSATION - 1):]

    sessions.set(conversation_id, history)

    async def generate() -> AsyncGenerator[str, None]:
        """SSE event generator with agent loop."""
        import anthropic

        print(f"[Assistant] Starting chat for conversation {conversation_id}", flush=True)
        yield sse_event("start", {"conversation_id": conversation_id})

        try:
            print("[Assistant] Creating Anthropic client...", flush=True)
            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            print("[Assistant] Client created, starting stream...", flush=True)

            loop_count = 0
            max_loops = 8

            nonlocal history

            while loop_count < max_loops:
                loop_count += 1

                # Stream response from Claude
                accumulated_text = ""
                response_content = []
                stop_reason = None

                print(f"[Assistant] Loop {loop_count}: calling Anthropic API...", flush=True)
                async with client.messages.stream(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=4096,
                    system=[{
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"}
                    }],
                    tools=TOOL_DEFINITIONS,
                    messages=history,
                ) as stream:
                    print("[Assistant] Stream opened, reading events...", flush=True)
                    async for event in stream:
                        if event.type == "content_block_delta":
                            if hasattr(event.delta, "text"):
                                yield sse_event("text", {"delta": event.delta.text})
                                accumulated_text += event.delta.text

                    # Get final message
                    response = await stream.get_final_message()
                    response_content = response.content
                    stop_reason = response.stop_reason

                    # Log usage for monitoring
                    if response.usage:
                        print(f"[Assistant] Usage: input={response.usage.input_tokens}, "
                              f"output={response.usage.output_tokens}, "
                              f"cache_read={getattr(response.usage, 'cache_read_input_tokens', 0)}")

                # Add assistant response to history
                history.append({
                    "role": "assistant",
                    "content": response_content
                })
                sessions.set(conversation_id, history)

                # If not a tool use, we're done
                if stop_reason != "tool_use":
                    break

                # Execute tools
                tool_results = []
                for block in response_content:
                    if block.type == "tool_use":
                        # Emit status event
                        summary = get_tool_summary(block.name, block.input)
                        yield sse_event("tool", {"name": block.name, "summary": summary})

                        # Execute tool
                        result = run_tool(block.name, block.input)

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result)
                        })

                # Add all tool results in a single user message
                history.append({
                    "role": "user",
                    "content": tool_results
                })
                sessions.set(conversation_id, history)

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


@router.delete("/chat/{conversation_id}")
async def clear_conversation(conversation_id: str):
    """Clear a conversation from memory."""
    if conversation_id in sessions:
        del sessions[conversation_id]
        return {"message": "Conversation cleared"}
    return {"message": "Conversation not found (may have already expired)"}
