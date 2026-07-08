# 33 — AI Assistant Implementation Plan ("Ask PDM")

**Status:** Plan — ready for implementation
**Author:** Planning session, 2026-07-08
**Goal:** Add a chat assistant (Claude) that can answer questions against live Supabase data and fetch files for the user.

Example interactions this must support:

- *"How many pipe hangers are in assembly csa00010?"* → assistant expands the BOM tree, counts matching child items, answers in plain language.
- *"Can you pull me the print of csp00200?"* → assistant looks up the item's PDF file, generates a signed download URL, and returns a clickable link.

---

## 1. Architecture Overview

```
Vue Chat View ──POST /api/assistant/chat (SSE)──▶ FastAPI assistant route
                                                      │
                                                      ├─▶ Anthropic API (claude-opus-4-8, streaming)
                                                      │      ▲ tool_use requests
                                                      │      │ tool_result responses
                                                      └─▶ Tool executors → get_supabase_admin()
                                                             (read-only queries + signed URLs)
```

**Key decisions (settled — do not re-litigate):**

1. **The agent loop runs server-side in FastAPI.** The Anthropic API key never reaches the browser. The frontend only sends chat text and receives streamed events.
2. **Claude gets a fixed set of read-only tools, NOT raw SQL access.** No `execute_sql` tool. Each tool is a Python function wrapping the same query logic the existing routes use. This bounds what the assistant can do to safe reads.
3. **Data reads use `get_supabase_admin()`** — same convention as every existing read route (RLS `SELECT` is restricted to the `authenticated` role, and the anon client returns 0 rows; see comment at `backend/app/routes/items.py:61-64`).
4. **The endpoint itself requires a logged-in user.** Add a real FastAPI auth dependency (the codebase currently has none — `get_current_user` in `auth.py` is a route handler, not a `Depends`).
5. **Model: `claude-opus-4-8`** with adaptive thinking and streaming. (Sonnet 5 is a cheaper fallback if cost becomes a concern, but default to Opus.)
6. **Conversation state lives on the backend** in an in-memory session dict keyed by `conversation_id` (single server, 3 users — no need for persistence in v1). The full message array including `tool_use`/`tool_result` blocks stays server-side; the client only ever sees text.

---

## 2. Prerequisites / User Action Required

- **`ANTHROPIC_API_KEY`** must be added to `backend/.env`. Jack said he has an API key from the VetBox-Pro project and will supply it. The implementation must fail gracefully (HTTP 503 with a clear message) if the key is unset, not crash at import time.
- Add `anthropic>=0.50` to `backend/requirements.txt` (`httpx` is already present; the SDK manages its own HTTP).

---

## 3. Backend Implementation

### 3.1 Config — `backend/app/config.py`

Add one field to `Settings`:

```python
anthropic_api_key: str = ""   # ANTHROPIC_API_KEY in .env
```

### 3.2 Auth dependency — `backend/app/routes/assistant.py` (or a new `app/dependencies.py`)

Reuse the token-verification logic from `auth.py:13-29` as a proper dependency:

```python
async def require_user(authorization: str = Header(...)) -> dict:
    """Verify Supabase JWT from the Authorization header; 401 on failure."""
    token = authorization.removeprefix("Bearer ").strip()
    supabase = get_supabase_client()
    user = supabase.auth.get_user(token)   # raises / returns None on bad token
    if not user or not user.user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"auth_id": user.user.id, "email": user.user.email}
```

### 3.3 Tools — `backend/app/services/assistant_tools.py` (new file)

Six read-only tools. Each is a plain function returning a JSON-serializable dict/list, plus a matching Anthropic tool definition. **Reuse the query logic from the existing routes rather than calling the HTTP endpoints** (no self-HTTP; import/share the code or duplicate the short queries).

| Tool | Backing logic | Purpose |
|---|---|---|
| `search_items(query, limit=20)` | `items.py` list route (`ilike` on `item_number`/`name`) | Find items by number fragment or name ("pipe hanger") |
| `get_item(item_number)` | `GET /api/items/{n}` logic | Full item detail + project name + file list. Lowercase the input. |
| `get_bom_tree(item_number, max_depth=10)` | `bom.py:30` recursive tree | Assembly explosion — the tool for "how many X in assembly Y" |
| `get_where_used(item_number)` | `bom.py:71` | Reverse BOM |
| `list_item_files(item_number, file_type=None)` | `files.py:267` logic, resolving item_number → item_id first | List files; `file_type="PDF"` = prints/drawings |
| `get_file_download_link(file_id)` | `files.py:430-466` signed-URL logic | Returns `{url, filename, expires_in}` — a 1-hour Supabase Storage signed URL |

Implementation notes:

- **Tool descriptions must state *when* to call them**, not just what they do (this measurably improves triggering on current Opus models). E.g. for `get_bom_tree`: *"Call this when the user asks what an assembly contains, how many of a part are used, or anything about assembly structure. Returns the full recursive BOM tree with quantities."*
- **Quantity math note in the tool description:** total count of a child part = sum over every occurrence of (its quantity × the product of all ancestor quantities). Claude handles this well when the tree includes per-node `quantity`, but say it explicitly in the system prompt so counts are rolled up correctly.
- **Item numbers are always lowercased** before querying (existing convention).
- Errors return a `tool_result` with `is_error: True` and a human-readable message ("Item 'csp9999' not found") so Claude can recover / ask the user.
- Cap `get_bom_tree` serialized output (e.g. trim to item_number, name, quantity, lifecycle_state per node) — the raw tree endpoint returns full item objects and deep trees would waste tokens.

### 3.4 Chat route — `backend/app/routes/assistant.py` (new file)

Follow the existing registration convention: `router = APIRouter(prefix="/assistant", tags=["assistant"])`, export in `app/routes/__init__.py`, add `app.include_router(assistant_router, prefix="/api")` in `main.py`.

**Endpoints:**

```
POST /api/assistant/chat          body: {conversation_id: str | null, message: str}
                                  returns: text/event-stream (SSE)
DELETE /api/assistant/chat/{conversation_id}    clears a conversation
```

**SSE event protocol** (one JSON object per `data:` line):

| event | payload | meaning |
|---|---|---|
| `start` | `{conversation_id}` | new/continued conversation id |
| `text` | `{delta}` | incremental assistant text |
| `tool` | `{name, summary}` | "Looking up BOM for csa00010…" status line for the UI |
| `done` | `{}` | turn complete |
| `error` | `{message}` | fatal error for this turn |

**Agent loop** (manual loop — we need to interleave SSE emission with tool execution; the SDK tool runner doesn't fit a streaming SSE generator cleanly):

```python
import anthropic
client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

# inside an async generator used by StreamingResponse:
while True:
    with client.messages.stream(
        model="claude-opus-4-8",
        max_tokens=8192,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT_BLOCKS,      # with cache_control on last block
        tools=TOOL_DEFINITIONS,
        messages=history,
    ) as stream:
        for event in stream:
            # forward text_delta events as SSE "text" events
        response = stream.get_final_message()

    history.append({"role": "assistant", "content": response.content})

    if response.stop_reason != "tool_use":
        break

    tool_results = []
    for block in response.content:
        if block.type == "tool_use":
            # emit SSE "tool" status event, then execute
            result = run_tool(block.name, block.input)   # from assistant_tools.py
            tool_results.append({"type": "tool_result",
                                 "tool_use_id": block.id,
                                 "content": json.dumps(result)})
    history.append({"role": "user", "content": tool_results})
```

Details that matter:

- The `anthropic` SDK is sync; run the loop in a thread (`run_in_threadpool` / `anyio.to_thread`) feeding an `asyncio.Queue` that the SSE generator drains — or use `anthropic.AsyncAnthropic`, which is the cleaner option. **Prefer `AsyncAnthropic`** with `async with client.messages.stream(...)`.
- Execute multiple `tool_use` blocks from one response and return **all** results in a **single** user message (splitting them degrades parallel tool use).
- Cap the loop at ~8 iterations; on hitting the cap, emit an error event.
- **Prompt caching:** system prompt and tool definitions are stable — put `cache_control: {"type": "ephemeral"}` on the last system block. Keep the system prompt byte-identical between requests (no timestamps in it).
- If `settings.anthropic_api_key` is empty → 503 "AI assistant is not configured (missing ANTHROPIC_API_KEY)".
- Session store: module-level `dict[str, list]` with a max size (e.g. 50 conversations, LRU-evict) and per-conversation history cap (~40 messages). `conversation_id = uuid4().hex` minted on first message.

### 3.5 System prompt

Store as a module constant. Content to include:

- Role: "You are the PDM assistant for a small sheet-metal fab shop. You answer questions about parts, assemblies, BOMs, files, and projects using the provided tools. Users: Jack (CAD engineer), Dan (PM), Shop."
- Domain context: item number format (`abc####`, lowercase; prefixes `mmc` = McMaster, `spn` = supplier, `zzz` = reference), lifecycle states (Design/Review/Released/Obsolete), file types (PDF = print/drawing, STEP, DXF, SVG, CAD).
- BOM counting rule (multiply quantities down the tree, sum across occurrences; show the math briefly).
- File delivery rule: "When the user asks for a print/drawing/file, call `list_item_files` then `get_file_download_link`, and present the result as a markdown link: `[csp00200 print (PDF)](url)`. Mention the link expires in 1 hour."
- Grounding rule: "Only state facts returned by tools. If a tool returns nothing, say so — never invent part data."
- Style: concise, plain language; tables for BOM listings.

---

## 4. Frontend Implementation

### 4.1 New files

| File | Purpose |
|---|---|
| `src/views/AssistantView.vue` | Chat page: message list, input box, streaming render |
| `src/stores/assistant.ts` | Pinia store: `messages[]`, `conversationId`, `sendMessage()`, `clear()` |
| `src/services/assistantApi.ts` | SSE client (can't reuse `apiCall` — it calls `.json()`) |

### 4.2 SSE client

Reuse the token logic from `services/supabase.ts` (`apiCall`), but read the body stream:

```ts
const { data: { session } } = await supabase.auth.getSession()
const res = await fetch('/api/assistant/chat', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json',
             Authorization: `Bearer ${session?.access_token}` },
  body: JSON.stringify({ conversation_id, message }),
})
// read res.body via ReadableStream reader, split on newlines, parse `data:` JSON lines
```

(Native `EventSource` doesn't support POST bodies or auth headers — hence fetch-streaming.)

### 4.3 Chat UI (AssistantView.vue)

- **Light PDM theme** (this is a PDM-wide feature, not MRP-specific) — tokens from `.claude/agents/style.md`; PrimeVue components + scoped CSS, no Tailwind.
- Message bubbles (user right / assistant left), an inline muted status line while a `tool` event is active ("Looking up BOM for csa00010…"), auto-scroll, disabled input while streaming, "New conversation" button.
- **Render assistant text as markdown** (add `marked` + `dompurify`, ~5 KB) so file links and BOM tables work. Links open in a new tab (`target="_blank" rel="noopener"`). Sanitize with DOMPurify — the text includes tool data, treat as untrusted HTML.
- Suggested empty-state prompts: "How many parts are in assembly …?", "Pull me the print of …", "What's the lifecycle state of …?"

### 4.4 Wiring

- Route in `src/router/index.ts`: `{ path: '/assistant', name: 'assistant', component: () => import('../views/AssistantView.vue'), meta: { requiresAuth: true } }`.
- Nav card in `HomeView.vue` `tools` array ("AI Assistant — ask questions about parts, BOMs, and prints").
- Delegate a review pass to the **style** agent after the view is built.

---

## 5. Implementation Order

1. **Backend foundation** — `anthropic` dep, `Settings.anthropic_api_key`, `require_user` dependency. *(delegate to `supabase` agent if touching auth conventions)*
2. **Tools** — `assistant_tools.py` with the 6 tools + unit-testable `run_tool()` dispatcher.
3. **Chat route** — SSE endpoint with agent loop, session store, prompt caching.
4. **Backend smoke test** — `curl -N` the SSE endpoint with the two canonical questions (pipe hangers count; csp00200 print) against real data.
5. **Frontend** — SSE client → store → view → route/nav card.
6. **Style review** (`style` agent) + **documentation** (`documentation` agent: update this doc's status, add to README index).

## 6. Testing Checklist

- [ ] "How many pipe hangers are in assembly csa00010?" → correct rolled-up count with brief math.
- [ ] "Pull me the print of csp00200" → working signed-URL markdown link, expiry mentioned.
- [ ] Item that doesn't exist → graceful "not found", no hallucinated data.
- [ ] Multi-turn follow-up ("what about its where-used?") uses conversation context.
- [ ] Request without a valid JWT → 401. Missing API key → 503 with clear message.
- [ ] Deep assembly (max_depth) doesn't blow token limits (tree trimming works).
- [ ] Second question in a session shows `cache_read_input_tokens > 0` (log usage per turn).

## 7. Explicit Non-Goals (v1)

- No write operations (lifecycle changes, checkouts, BOM edits) — read-only.
- No raw SQL tool for the model.
- No persistent chat history across server restarts.
- No MRP-specific tools (routing, costing) — natural phase 2 once v1 works.
- No floating chat widget on other pages — dedicated view only for now.

## 8. Cost Note

Opus 4.8 is $5/$25 per MTok. With prompt caching on the system prompt + tools, a typical Q&A turn should run well under a cent; BOM-heavy turns a few cents. At this team's usage (3 users) cost is negligible. If it ever matters, swap the model string to `claude-sonnet-5` — no other code changes needed.
