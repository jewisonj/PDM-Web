# PDM AI Assistant

**Status:** Active
**Version:** v3.9.1+
**Location:** `/mrp/assistant` (MRP side navigation)
**Model:** Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`)
**Access:** Read-only tools for PDM and MRP data (items, BOMs, files, projects/timelines, costs, routing, materials, work queue)

---

## Overview

The PDM AI Assistant is a conversational interface for querying parts, BOMs, files, and projects. Users can ask natural-language questions like "How many parts are in assembly csa00010?" or "Pull me the print of csp00200" and receive immediate answers with data grounded in the PDM database.

**Key Features:**
- Natural language search for items, assemblies, and files
- BOM tree expansion and part counting
- Where-used lookup (reverse BOM)
- File download link generation (PDFs, DXFs, etc.)
- Streaming responses with real-time tool status
- Conversation history (in-memory, session-scoped)

**Intentional Limitations (v1):**
- **Read-only** - Cannot modify data, create items, or trigger workflows
- **No authentication** - Skipped JWT for v1 (uses admin Supabase client)
- **In-memory sessions** - Conversations cleared on server restart
- **Max 50 conversations cached** (LRU eviction)
- **Max 40 messages per conversation** (auto-trimmed to prevent runaway context)
- **Max 8 tool calls per turn** (prevents infinite loops)

---

## Architecture

### Backend Components

#### 1. Chat Endpoint (`backend/app/routes/assistant.py`)

**POST /api/assistant/chat**

SSE (Server-Sent Events) streaming endpoint with server-side agent loop.

**Request:**
```json
{
  "conversation_id": "abc123xyz",  // Optional - creates new if omitted
  "message": "How many parts are in csa00010?"
}
```

**Response Stream (SSE events):**
- `start` - `{conversation_id}` - Conversation started
- `text` - `{delta}` - Incremental text chunk
- `tool` - `{name, summary}` - Tool execution status (e.g., "Expanding BOM for csa00010...")
- `done` - `{}` - Turn complete
- `error` - `{message}` - Fatal error

**Agent Loop:**
1. Send user message to Claude with tool definitions
2. Stream response text to frontend
3. If `stop_reason == "tool_use"`, execute tools server-side
4. Send tool results back to Claude
5. Repeat until text response (max 8 iterations)

**DELETE /api/assistant/chat/{conversation_id}**

Clears a conversation from the server's in-memory cache.

**Session Management:**
- LRU cache with max 50 conversations (`LRUCache` class)
- Each conversation stores full message history (user + assistant messages)
- History trimmed to 40 messages max (keeps first + last N-1)

**Prompt Caching:**
```python
system=[{
    "type": "text",
    "text": SYSTEM_PROMPT,
    "cache_control": {"type": "ephemeral"}  # Caches system prompt for cost savings
}]
```

#### 2. Tool Implementations (`backend/app/services/assistant_tools.py`)

Thirteen read-only tools for querying PDM and MRP data via Supabase admin client:

**PDM tools:**

| Tool | Description | Example Use |
|------|-------------|-------------|
| `search_items` | Search by item number or name fragment | "Find parts with 'bracket'" |
| `get_item` | Get full details for a specific item | "What's the material of csp00200?" |
| `get_bom_tree` | Recursive BOM expansion with quantities | "How many parts in csa00010?" |
| `get_where_used` | Find parent assemblies (reverse BOM) | "Where is csp00100 used?" |
| `list_item_files` | List files for an item (with type filter) | "What files are for stp02810?" |
| `get_file_download_link` | Generate signed download URL (1 hour expiry) | "Pull me the print of csp00200" |

**MRP tools (added 2026-07):**

| Tool | Description | Example Use |
|------|-------------|-------------|
| `list_mrp_projects` | List MRP projects with timelines (status, start/due dates) | "What projects are due soon?" |
| `get_mrp_project` | One project's detail + completion progress by station | "How is WM2121 going?" |
| `get_project_cost_estimate` | Full cost estimate (labor/material/outsourced/purchased + overhead); reuses `services/cost_estimate.py`, same math as the MRP cost page | "What does project RX0203 cost?" |
| `get_item_routing` | Manufacturing routing steps with stations and times | "How is csp00200 made?" |
| `list_work_queue_tasks` | Background task queue with status/errors | "Any failed DXF tasks?" |
| `get_pricing_settings` | Cost settings + workstation hourly rates | "What's our overhead multiplier?" |
| `list_raw_materials` | Raw material prices and stock levels | "What's CS sheet running per pound?" |

MRP project tools accept a `project_code` (exact or partial, case-insensitive). Cost estimate results are truncated to the top N line items by extended cost (default 20) to control token usage; totals always include all items.

**Tool Execution Flow:**
1. Claude calls tool via `tool_use` block
2. Backend emits `tool` SSE event with human-readable summary
3. Backend executes tool function (DB query via Supabase)
4. Tool result sent back to Claude as JSON
5. Claude synthesizes result into natural language response

**Error Handling:**
- Tool failures return `{"error": "..."}` dict
- Claude reports errors gracefully to user
- Unknown tools return `{"error": "Unknown tool: ..."}`

**Data Access:**
- All tools use `get_supabase_admin()` (service role key)
- No RLS policies enforced (v1 skips auth)
- Queries directly against `items`, `files`, `bom`, `projects`, `mrp_projects`, `mrp_project_parts`, `routing`, `routing_materials`, `workstations`, `raw_materials`, `cost_settings`, `part_completion`, and `work_queue` tables
- Everything is strictly read-only - no tool inserts, updates, or deletes data

#### 3. Configuration (`backend/app/config.py`)

```python
class Settings(BaseSettings):
    # ...
    anthropic_api_key: str = ""  # Load from ANTHROPIC_API_KEY env var
```

Set in `backend/.env`:
```bash
ANTHROPIC_API_KEY=sk-ant-...
```

**Dependencies** (`backend/requirements.txt`):
```
anthropic>=0.50.0
```

### Frontend Components

#### 1. Chat View (`frontend/src/views/MrpAssistantView.vue`)

Full-screen chat interface with:
- **Header:** Back to dashboard, title, "New Chat" button
- **Empty state:** Welcome message + 4 suggested prompts
- **Messages:** User bubbles (right, blue) + assistant bubbles (left, dark)
- **Input area:** Textarea with send button, disabled during streaming
- **Auto-scroll:** Scrolls to bottom on new messages

**Suggested Prompts:**
```typescript
[
  'How many parts are in assembly csa00010?',
  'Pull me the print of csp00200',
  "What's the lifecycle state of stp02810?",
  'Where is csp00100 used?',
]
```

**Markdown Rendering:**
- Uses `marked` for parsing, `DOMPurify` for XSS safety
- Code blocks styled with dark background (`#0f172a`)
- Tables auto-styled with borders and header background
- Links open in new tab (`target="_blank"`)

**Tool Status Indicators:**
- Shows spinner + summary text (e.g., "Expanding BOM for csa00010...")
- Displayed below assistant message bubble
- Cleared when text starts arriving

**Typing Indicator:**
- Three animated dots while waiting for first text chunk
- Hidden once tool status or text arrives

#### 2. Store (`frontend/src/stores/assistant.ts`)

Pinia store managing conversation state:

```typescript
interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  toolStatus?: string  // Shows "Looking up..." during tool execution
}
```

**Actions:**
- `sendMessage(content)` - Sends message, streams response
- `clear()` - Clears local state + server conversation

**Computed:**
- `hasMessages` - True if conversation has started

**SSE Event Handling:**
- `onStart` - Stores conversation ID
- `onText` - Appends delta to last assistant message
- `onTool` - Updates `toolStatus` on last assistant message
- `onDone` - Clears tool status
- `onError` - Sets error state, removes empty assistant message

#### 3. API Client (`frontend/src/services/assistantApi.ts`)

SSE streaming client using fetch + ReadableStream (EventSource doesn't support POST bodies):

```typescript
export async function sendChatMessage(
  message: string,
  conversationId: string | null,
  callbacks: ChatCallbacks
): Promise<void>
```

**Callbacks:**
- `onStart(conversationId)` - Conversation started
- `onText(delta)` - Text chunk received
- `onTool(name, summary)` - Tool executing
- `onDone()` - Response complete
- `onError(message)` - Error occurred

**SSE Parsing:**
- Buffers incomplete lines
- Parses `event:` and `data:` lines
- Emits event on empty line (SSE delimiter)

#### 4. Routing (`frontend/src/router/index.ts`)

```typescript
{
  path: '/mrp/assistant',
  name: 'mrp-assistant',
  component: () => import('../views/MrpAssistantView.vue'),
  meta: { requiresAuth: true }
}
```

**Dashboard Integration** (`MrpDashboardView.vue`):
- "Ask PDM" button in MRP navigation bar
- Icon: `pi-comments`
- Nav dot styled with assistant color

---

## System Prompt

The assistant uses this system prompt (cached for efficiency):

```
You are the PDM assistant for a small sheet-metal fabrication shop. You answer questions about parts, assemblies, BOMs, files, and projects using the provided tools.

**Users:** Jack (CAD engineer), Dan (PM), Shop (shared account).

**Domain context:**
- Item numbers follow the format `abc####` (3 letters + 4-6 digits), always lowercase. Examples: `csp0030`, `wma20120`, `stp02810`.
- Prefixes: `mmc` = McMaster-Carr, `spn` = supplier part, `zzz` = reference/phantom.
- Lifecycle states: Design, Review, Released, Obsolete.
- File types: PDF (prints/drawings), STEP (3D CAD), DXF (flat patterns), SVG (bend drawings), CAD (native Creo files).

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
- Item numbers should be shown in lowercase monospace: `csp00200`.
```

**Key Prompt Engineering Decisions:**
- **BOM counting rule** - Explicitly teaches multiplying ancestor quantities (prevents common mistake of summing only direct children)
- **File delivery workflow** - Guides multi-step tool calling for download links
- **Grounding instruction** - Prevents hallucination of part data
- **Style guide** - Enforces lowercase item numbers, markdown tables

---

## Usage Examples

### Example 1: Search for Parts

**User:** "Find parts with 'bracket' in the name"

**Tool Calls:**
1. `search_items(query="bracket", limit=20)`

**Response:**
```
I found 12 parts matching "bracket":

| Item Number | Name | Lifecycle State | Material |
|-------------|------|-----------------|----------|
| csp00150 | L-Bracket | Released | A36 Steel |
| csp00151 | Mounting Bracket | Released | Aluminum 6061 |
...
```

### Example 2: BOM Expansion

**User:** "How many parts are in assembly csa00010?"

**Tool Calls:**
1. `get_bom_tree(item_number="csa00010", max_depth=10)`

**Response:**
```
Assembly `csa00010` contains 47 total parts:

- 2x csp00100 (Top Panel)
- 4x csp00101 (Side Bracket) - each panel uses 2
- 8x mmc95479a110 (M6 Socket Head Cap Screw) - 2 per bracket
...

Total: 47 parts
```

**Behind the scenes:** Claude recursively multiplies quantities down the tree (2 panels × 2 brackets each = 4 brackets, then 4 brackets × 2 screws each = 8 screws).

### Example 3: File Download

**User:** "Pull me the print of csp00200"

**Tool Calls:**
1. `list_item_files(item_number="csp00200", file_type="PDF")`
2. `get_file_download_link(file_id="uuid-from-step-1")`

**Response:**
```
Here's the print for `csp00200`:

[csp00200_rev_A.pdf](https://supabase.co/storage/v1/object/sign/pdm-files/...)

This link expires in 1 hour.
```

### Example 4: Where-Used

**User:** "Where is csp00100 used?"

**Tool Calls:**
1. `get_where_used(item_number="csp00100")`

**Response:**
```
Part `csp00100` is used in 3 assemblies:

| Assembly | Name | Quantity | Lifecycle State |
|----------|------|----------|-----------------|
| csa00010 | Main Frame Assembly | 2 | Released |
| csa00012 | Secondary Frame | 1 | Review |
| csa00015 | Test Assembly | 4 | Design |
```

---

## Performance & Cost Optimization

### Prompt Caching

System prompt is marked with `cache_control: {"type": "ephemeral"}` to enable Claude's prompt caching. This reduces:
- **Input tokens** from ~500 to ~50 per turn (after first turn)
- **Cost** by ~90% on cached turns
- **Latency** by 20-30ms per turn

**Cache lifetime:** ~5 minutes of inactivity

### Token Usage Logging

Backend logs usage for each turn:
```python
print(f"[Assistant] Usage: input={response.usage.input_tokens}, "
      f"output={response.usage.output_tokens}, "
      f"cache_read={getattr(response.usage, 'cache_read_input_tokens', 0)}")
```

**Typical usage:**
- **First turn:** 500 input tokens, 200 output tokens
- **Cached turns:** 50 input tokens (450 cached), 200 output tokens
- **BOM expansion:** +500 tokens for large trees

### LRU Cache Limits

- **Max 50 conversations** - Oldest evicted first
- **Max 40 messages per conversation** - Auto-trimmed to keep context fresh
- **Max 8 tool calls per turn** - Prevents runaway loops

**Memory footprint:** ~5 KB per message × 40 messages × 50 conversations = ~10 MB

---

## Security Considerations

### v1 Limitations (Accepted Risk)

**No authentication on chat endpoint:**
- Skipped JWT validation for v1 simplicity
- Uses Supabase admin client (bypasses RLS)
- Acceptable for internal-only deployment on Tailnet

**Mitigations:**
- Read-only tools (no writes/deletes/updates)
- CORS restricted to known origins (localhost, Tailnet)
- No PII in PDM data (only part numbers, names, materials)

**Future (v2):**
- Add JWT auth to `/api/assistant/chat`
- Use user-scoped Supabase client (enforce RLS)
- Add rate limiting (per-user)

### XSS Protection

**Frontend sanitization:**
- All markdown content sanitized with `DOMPurify`
- Code blocks, tables, and links allowed
- Script tags, event handlers stripped

**Backend sanitization:**
- SQL injection prevented by Supabase client (parameterized queries)
- No raw SQL execution

### File Download Security

**Signed URLs:**
- `get_file_download_link` generates Supabase signed URLs (1 hour expiry)
- URLs scoped to specific file path in storage bucket
- No directory traversal possible

**Storage buckets:**
- `pdm-files` bucket has RLS policies (though admin client bypasses)
- Future: Enforce RLS after adding auth to assistant

---

## Troubleshooting

### Assistant Not Responding

**Symptom:** Clicking "Send" does nothing, no error shown.

**Diagnosis:**
1. Check backend logs for `[Assistant]` prefix:
   ```bash
   cd backend
   uvicorn app.main:app --reload --port 8001
   ```
2. Look for "missing ANTHROPIC_API_KEY" error

**Fix:**
- Set `ANTHROPIC_API_KEY` in `backend/.env`
- Restart backend service

### Streaming Cuts Off Mid-Response

**Symptom:** Response stops after 1-2 sentences, no error.

**Diagnosis:**
- Check for `max_loops` reached (backend logs "Too many tool calls")
- Check for timeout (SSE stream closed by nginx/proxy)

**Fix:**
- Increase `max_loops` in `assistant.py` if legitimate multi-tool query
- Check nginx/proxy buffering settings (`X-Accel-Buffering: no` header)

### Tool Execution Slow

**Symptom:** Tool status shows for 5+ seconds.

**Diagnosis:**
- Check Supabase query performance (especially `get_bom_tree` on deep assemblies)
- Look for N+1 queries in tool implementations

**Fix:**
- Add indexes to `bom` table (`parent_item_id`, `child_item_id`)
- Optimize recursive BOM query (consider materialized path or closure table)

### "Item Not Found" for Valid Item

**Symptom:** Claude says "Item not found" for existing item.

**Diagnosis:**
- Check item number format (must be lowercase, e.g., `csp00200` not `CSP00200`)
- Verify item exists in DB: `SELECT * FROM items WHERE item_number = 'csp00200'`

**Fix:**
- Normalize input in tool functions (already done with `.lower().strip()`)
- Add fuzzy matching if user frequently mistypes

---

## Future Enhancements

### Planned (v2)

**Authentication:**
- Add JWT validation to `/api/assistant/chat`
- Pass user ID to tools for RLS enforcement
- Show user's checkout status in responses

**Persistent Conversations:**
- Store conversations in `assistant_conversations` table
- Allow resuming old conversations by ID
- Add conversation search/history view

**Expanded Tools:**
- `get_checkout_status(item_number)` - Check if item is checked out
- `search_projects(query)` - Find projects by name/code
- `get_project_schedule(project_code)` - Show project timeline
- `get_work_queue_status()` - Check DXF/SVG generation status

**Multi-Turn Context:**
- Remember user preferences (e.g., "always show material")
- Reference previous questions ("and what about csp00201?")
- Summarize conversations for handoff to human

### Considered (Low Priority)

**Write Operations:**
- `create_checkout(item_number)` - Check out item (requires auth)
- `submit_feedback(item_number, comment)` - Add item comment
- Requires extensive auth, validation, audit logging

**Image Understanding:**
- Upload PDFs/drawings, ask questions about geometry
- Requires vision-capable model (Claude Opus 4)
- Storage for uploaded images

**Voice Input:**
- Shop floor workers ask questions hands-free
- Requires WebRTC + speech-to-text integration

---

## Testing

### Manual Testing Checklist

**Basic Functionality:**
- [ ] Search for parts by name
- [ ] Search for parts by item number fragment
- [ ] Get details for specific item
- [ ] Expand BOM tree (shallow, 1-2 levels)
- [ ] Expand BOM tree (deep, 5+ levels)
- [ ] Count total parts in assembly
- [ ] Find where-used for part
- [ ] List files for item
- [ ] Request file download link

**Edge Cases:**
- [ ] Search with no results
- [ ] Get non-existent item
- [ ] BOM for part (not assembly)
- [ ] Where-used for unused part
- [ ] Item with no files
- [ ] Request file for wrong item

**UI/UX:**
- [ ] Suggested prompts work
- [ ] Messages auto-scroll
- [ ] Markdown renders correctly
- [ ] Tool status shows and clears
- [ ] Typing indicator animates
- [ ] Error banner displays
- [ ] "New Chat" clears state
- [ ] Back button returns to dashboard

**Performance:**
- [ ] First response < 3 seconds
- [ ] Cached responses < 1 second
- [ ] BOM expansion < 5 seconds (100-part assembly)
- [ ] No memory leaks (check after 20+ turns)

### Example Test Queries

```
# Search
"Find parts with 'bracket'"
"Search for csp002"

# Item details
"What's the material of csp00200?"
"Tell me about stp02810"

# BOM
"How many parts are in csa00010?"
"Show me the BOM for csa00015"

# Where-used
"Where is csp00100 used?"
"What assemblies contain mmc95479a110?"

# Files
"List files for csp00200"
"Pull me the print of stp02810"
"Get the DXF for csp00150"

# Edge cases
"Find parts with 'zzzzzz'" (no results)
"Tell me about invalid123" (not found)
"Pull print for csa00010" (assembly, not part)
```

---

## Maintenance

### Monitoring

**Key Metrics:**
- API requests/day to `/api/assistant/chat`
- Average tokens per turn (input, output, cached)
- Tool call distribution (which tools used most)
- Error rate (4xx, 5xx, timeout)
- Average response latency

**Logs to Watch:**
```bash
# Backend (SSE events, tool execution, errors)
tail -f backend/logs/assistant.log

# Look for:
[Assistant] Starting chat for conversation abc123
[Assistant] Usage: input=500, output=200, cache_read=0
[Assistant] Error: API error: rate limit exceeded
```

### Cost Monitoring

**Anthropic pricing (as of 2026-07):**
- Input: $3/M tokens
- Output: $15/M tokens
- Cached input: $0.30/M tokens (10× cheaper)

**Estimated costs:**
- **Typical query:** 500 input + 200 output = $0.0045
- **Cached query:** 50 input + 200 output = $0.0032 (30% savings)
- **Heavy BOM query:** 1000 input + 500 output = $0.0105

**Monthly estimate (100 queries/day):**
- 100 queries × 30 days × $0.003 avg = **$9/month**

### System Prompt Updates

When modifying `SYSTEM_PROMPT` in `assistant.py`:

1. **Test thoroughly** - Small changes affect all responses
2. **Clear cache** - Restart backend to invalidate old cached prompts
3. **Document changes** - Add to "Version History" section
4. **Consider cost** - Longer prompts = more tokens (but cached!)

**Common reasons to update:**
- New lifecycle states added
- New file types introduced
- Tool calling patterns need refinement
- User feedback on response style

### Tool Schema Updates

When adding/modifying tools in `assistant_tools.py`:

1. **Update `TOOL_DEFINITIONS`** - Add/modify Anthropic tool schema
2. **Implement function** - Add to `TOOL_FUNCTIONS` dict
3. **Add summary** - Add to `TOOL_SUMMARIES` for status text
4. **Test with Claude** - Ensure Claude understands when to call it
5. **Update docs** - Document new tool here

**Example: Adding `get_project_schedule`**
```python
# 1. Definition
{
    "name": "get_project_schedule",
    "description": "Get project timeline and milestone dates.",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_code": {
                "type": "string",
                "description": "Project code (e.g., 'WAG-001')"
            }
        },
        "required": ["project_code"]
    }
}

# 2. Implementation
def get_project_schedule(project_code: str) -> dict:
    supabase = get_supabase_admin()
    # ... query project_milestones table ...
    return {"milestones": [...]}

# 3. Register
TOOL_FUNCTIONS["get_project_schedule"] = get_project_schedule
TOOL_SUMMARIES["get_project_schedule"] = "Loading project schedule..."
```

---

## Version History

### v3.9.1+ (2026-07-07) - Initial Release

**Added:**
- Backend chat endpoint with SSE streaming (`/api/assistant/chat`)
- 6 read-only tools for PDM data access
- Frontend chat UI at `/mrp/assistant`
- "Ask PDM" button in MRP dashboard
- Pinia store for conversation state
- SSE client with streaming support
- Markdown rendering with syntax highlighting
- Tool status indicators
- Prompt caching for cost optimization
- LRU session cache (max 50 conversations)

**Configuration:**
- `ANTHROPIC_API_KEY` in `backend/.env`
- `anthropic>=0.50.0` in `requirements.txt`
- Model: `claude-sonnet-4-5-20250929`

**Known Limitations:**
- No JWT auth (uses admin Supabase client)
- In-memory sessions only (lost on restart)
- No conversation history persistence
- No rate limiting
- No multi-user support

---

## Related Documentation

- `02-PDM-COMPLETE-OVERVIEW.md` - System architecture
- `03-DATABASE-SCHEMA.md` - Database tables used by tools
- `04-SERVICES-REFERENCE.md` - Backend API configuration
- `10-PDM-WEBSERVER-OVERVIEW.md` - Frontend UI patterns
- `14-SKILL-DEFINITION.md` - AI assistant skill definition (Claude Code agent)
- `20-COMMON-WORKFLOWS.md` - User workflows this feature supports

---

**Last Updated:** 2026-07-07
**Maintainer:** Documentation Agent
**Review Cycle:** After each major feature addition
