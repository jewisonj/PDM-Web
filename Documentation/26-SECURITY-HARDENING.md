# PDM-Web - Security Hardening Guide

**Security Architecture and Best Practices**
**Related Docs:** [23-SYSTEM-CONFIGURATION.md](23-SYSTEM-CONFIGURATION.md), [21-BACKUP-RECOVERY-GUIDE.md](21-BACKUP-RECOVERY-GUIDE.md)

---

## Security Architecture Overview

PDM-Web delegates authentication, authorization, and data protection to Supabase, a managed platform built on PostgreSQL. This significantly reduces the security surface compared to self-hosted systems.

### Security Layers

| Layer | Responsibility | Technology |
|-------|---------------|------------|
| Authentication | User identity verification | Supabase Auth (JWT-based) |
| Authorization | Data access control | Row Level Security (RLS) in PostgreSQL |
| Transport | Encrypted communication | HTTPS (Supabase), CORS (FastAPI) |
| API Access | Key-based access control | Anon key (public) + Service role key (admin) |
| Input Validation | Request sanitization | Pydantic schemas (FastAPI) |
| Session Management | Token lifecycle | Supabase Auth client (auto-refresh, persist) |
| Secret Management | Environment isolation | `.env` files, never committed to git |

---

## Supabase Auth Security

### How Authentication Works

1. The user enters their email and password in the Vue frontend
2. The Supabase JavaScript client sends credentials directly to Supabase Auth (HTTPS)
3. Supabase Auth verifies the credentials and returns a JWT access token and refresh token
4. The frontend stores the session in `localStorage` under the key `pdm-web-auth`
5. Subsequent API calls include the JWT in the `Authorization: Bearer <token>` header
6. The backend verifies the token via `supabase.auth.get_user(token)`

```typescript
// frontend/src/stores/auth.ts -- login flow
async function login(email: string, password: string) {
  const { error: authError } = await supabase.auth.signInWithPassword({
    email,
    password,
  })
  if (authError) throw authError
  await fetchUser()
}
```

### JWT Token Security

Supabase Auth issues JWTs signed with your project's JWT secret. Key properties:

- **Access tokens** expire after the configured JWT expiry time (default: 3600 seconds / 1 hour)
- **Refresh tokens** are long-lived and used to obtain new access tokens
- The frontend automatically refreshes expired tokens via `autoRefreshToken: true`
- Tokens are validated on every API call -- expired or tampered tokens are rejected

```typescript
// frontend/src/services/supabase.ts -- auto-retry on 401
if (response.status === 401 && retry) {
  const { data: { session: newSession } } = await supabase.auth.refreshSession()
  if (newSession) {
    return apiCall<T>(endpoint, options, false)  // Retry with new token
  }
}
```

### Password Security

Supabase Auth handles password storage and verification. Passwords are:

- Hashed using bcrypt with a strong work factor
- Never stored in plaintext
- Never transmitted to or processed by the PDM-Web backend

**Recommended password policy** (configure in Supabase Dashboard > Authentication > Policies):

- Minimum 8 characters (Supabase default)
- Require mix of character types if desired
- Consider enabling rate limiting on login attempts

### Session Management

The auth store in `frontend/src/stores/auth.ts` manages the session lifecycle:

- **Initialization:** On app load, `initialize()` checks for an existing session
- **Auth state changes:** `onAuthStateChange` listener handles `SIGNED_IN`, `SIGNED_OUT`, and `TOKEN_REFRESHED` events
- **Session persistence:** Sessions are stored in `localStorage` and survive page refreshes
- **Logout:** Clears the session both locally and on the Supabase server

```typescript
supabase.auth.onAuthStateChange(async (event, session) => {
  if (event === 'SIGNED_IN' && session) {
    await fetchUser()
  } else if (event === 'SIGNED_OUT') {
    user.value = null
  } else if (event === 'TOKEN_REFRESHED' && session) {
    await fetchUser()
  }
})
```

---

## API Key Management

PDM-Web uses two Supabase API keys with different privilege levels. Understanding the difference is critical for security.

### Anon Key (Public / Publishable)

- **Purpose:** Client-side operations, user-level database access
- **Used by:** Frontend (embedded at build time), backend (user-level queries)
- **Access level:** Restricted by Row Level Security policies
- **Safe to expose:** Yes -- this key is designed for client-side use
- **Configuration:** `VITE_SUPABASE_ANON_KEY` (frontend), `SUPABASE_ANON_KEY` (backend)

### Service Role Key (Admin / Secret)

- **Purpose:** Server-side operations that bypass RLS
- **Used by:** Backend only (file uploads, bulk BOM operations, admin queries)
- **Access level:** Full database access, bypasses all RLS policies
- **Safe to expose:** NO -- never expose in frontend code, URLs, or client responses
- **Configuration:** `SUPABASE_SERVICE_KEY` (backend only)

### Where Each Key is Used

```python
# backend/app/services/supabase.py
def get_supabase_client() -> Client:
    """Anon key -- respects RLS policies."""
    return create_client(settings.supabase_url, settings.supabase_anon_key)

def get_supabase_admin() -> Client:
    """Service role key -- bypasses RLS for admin operations."""
    return create_client(settings.supabase_url, settings.supabase_service_key)
```

The admin client is used in specific routes:
- `POST /api/files/upload` -- File upload from the bridge script (bypasses RLS to write file records)
- `POST /api/bom/bulk` -- Bulk BOM import (creates items and BOM entries)
- `GET /api/auth/me` -- User lookup by auth_id (reads from users table with admin privileges)
- `PATCH /api/items/{item_number}?upsert=true` -- Upsert operations from trusted services

### Key Rotation

If a key is compromised:

1. **Anon key compromised:** Generate a new anon key in Supabase Dashboard > Settings > API. Update `frontend/.env` and `backend/.env`. Rebuild and redeploy the frontend.

2. **Service role key compromised:** This is a critical incident. Immediately:
   - Generate a new service role key in Supabase Dashboard
   - Update `backend/.env`
   - Restart the backend
   - Review database logs for unauthorized writes
   - Check for unexpected data modifications

---

## Row Level Security (RLS)

Row Level Security is PostgreSQL's built-in mechanism for controlling which rows a user can read, insert, update, or delete. In Supabase, RLS is enforced when using the anon key; it is bypassed when using the service role key.

### RLS Policy Design

RLS policies should be enabled on all tables that contain user data. Policies should follow the principle of least privilege.

**Example policies for the PDM-Web schema:**

```sql
-- Enable RLS on tables
ALTER TABLE items ENABLE ROW LEVEL SECURITY;
ALTER TABLE files ENABLE ROW LEVEL SECURITY;
ALTER TABLE bom ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE lifecycle_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Items: All authenticated users can read, engineers can write
CREATE POLICY "items_select" ON items FOR SELECT
  TO authenticated USING (true);

CREATE POLICY "items_insert" ON items FOR INSERT
  TO authenticated WITH CHECK (true);

CREATE POLICY "items_update" ON items FOR UPDATE
  TO authenticated USING (true) WITH CHECK (true);

CREATE POLICY "items_delete" ON items FOR DELETE
  TO authenticated USING (true);

-- Files: All authenticated users can read, engineers can write
CREATE POLICY "files_select" ON files FOR SELECT
  TO authenticated USING (true);

CREATE POLICY "files_insert" ON files FOR INSERT
  TO authenticated WITH CHECK (true);

-- Users: Users can read all users, but only update their own record
CREATE POLICY "users_select" ON users FOR SELECT
  TO authenticated USING (true);

CREATE POLICY "users_update_own" ON users FOR UPDATE
  TO authenticated USING (auth.uid() = auth_id);
```

### Checking RLS Status

Use the Supabase Dashboard or SQL Editor to verify RLS is enabled:

```sql
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public';
```

### RLS and the Service Role Key

Operations using `get_supabase_admin()` bypass RLS entirely. This is intentional for:
- Backend-to-database writes from trusted services (upload bridge)
- Admin operations that need to access all data
- User creation/linking during authentication

Keep the service role key strictly on the backend. Never use it in frontend code.

---

## Transport Security (HTTPS)

### Supabase Connections

All communication with Supabase services uses HTTPS:

- **Database API:** `https://<ref>.supabase.co/rest/v1/` (PostgREST)
- **Auth API:** `https://<ref>.supabase.co/auth/v1/`
- **Storage API:** `https://<ref>.supabase.co/storage/v1/`

TLS certificates are managed by Supabase. No configuration is needed.

### Frontend to Backend

In development, the frontend communicates with the backend over HTTP (`http://localhost:8001`). This is acceptable for local development and Tailnet (which provides its own encryption layer).

In production with a single container deployment:
- The backend serves both the API and frontend on the same origin
- HTTPS should be terminated at the hosting provider's load balancer or reverse proxy (e.g., Fly.io provides automatic TLS)
- All external traffic should be HTTPS-only

### Signed URLs

File downloads use signed URLs generated by Supabase Storage. These URLs:

- Are time-limited (default: 1 hour)
- Are cryptographically signed -- cannot be forged
- Grant access to a specific file path only
- Expire automatically after the configured duration

```typescript
// frontend/src/services/storage.ts
const { data, error } = await supabase.storage
  .from(bucket)
  .createSignedUrl(path, 3600)  // Valid for 1 hour
```

---

## CORS Configuration

CORS (Cross-Origin Resource Sharing) controls which web origins can make requests to the FastAPI backend.

### Current Configuration

```python
# backend/app/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.cors_allow_all else settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Security Recommendations

- **Development:** `CORS_ALLOW_ALL=true` is acceptable when running locally or on a private Tailnet
- **Production (separate frontend/backend):** Set `CORS_ALLOW_ALL=false` and list specific allowed origins in `config.py`
- **Production (single container):** CORS is not needed because the frontend and API share the same origin

CORS does not apply to:
- Server-to-server requests (the upload bridge script)
- Direct Supabase client calls from the frontend (these go to `*.supabase.co`, which has its own CORS configuration)

---

## Frontend Security

### No Secrets in Client Code

The frontend contains only the Supabase anon key, which is designed to be public. The following should never appear in frontend code:

- `SUPABASE_SERVICE_KEY` or any service role key
- Database connection strings or passwords
- Admin API tokens
- Any key that grants elevated privileges

The anon key provides:
- Authentication (login/logout)
- Read/write access controlled by RLS policies
- Storage access controlled by storage policies

### Input Sanitization

Vue 3's template system automatically escapes HTML output, preventing XSS (Cross-Site Scripting) attacks. Do not use `v-html` with user-provided content.

### Session Storage

Auth sessions are stored in `localStorage` under the key `pdm-web-auth`. This means:
- Sessions persist across browser tabs and page refreshes
- Sessions are cleared on explicit logout
- `localStorage` is origin-scoped -- other domains cannot access the session

---

## Backend Security

### Input Validation with Pydantic

All API endpoints validate input using Pydantic schemas defined in `backend/app/models/schemas.py`. This prevents:

- SQL injection (data is parameterized by the Supabase client)
- Invalid data types reaching the database
- Malformed item numbers (enforced by regex)

```python
class ItemBase(BaseModel):
    item_number: str = Field(..., pattern=r"^[a-z]{3}\d{4,6}$")
    name: Optional[str] = None
    revision: str = "A"
    iteration: int = 1
    lifecycle_state: str = "Design"
    # ... additional fields with type validation
```

**Key validations:**
- `item_number` must match the pattern `^[a-z]{3}\d{4,6}$` (3 lowercase letters + 4-6 digits)
- UUIDs are validated as proper UUID format
- Numeric fields (mass, thickness, etc.) are validated as `float`
- String fields reject non-string input

### Authentication Verification

The `/api/auth/me` endpoint verifies JWT tokens from the frontend:

```python
@router.get("/me", response_model=User)
async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = authorization.split(" ")[1]
    auth_user = supabase.auth.get_user(token)

    if not auth_user or not auth_user.user:
        raise HTTPException(status_code=401, detail="Invalid token")
    # ... user lookup logic
```

### Error Handling

The backend avoids leaking internal details in error responses. Database errors are caught and returned with generic messages:

```python
except Exception as e:
    if "duplicate key" in str(e).lower():
        raise HTTPException(status_code=409, detail=f"Item {item.item_number} already exists")
    raise HTTPException(status_code=400, detail=str(e))
```

For production, consider further restricting error messages to avoid exposing database constraint names or internal paths.

### File Upload Security

File uploads via `/api/files/upload` include these protections:

- File content type is validated
- Files are uploaded to Supabase Storage (not stored on the local filesystem)
- The item must exist in the database before files can be uploaded for it
- The upload uses the admin client, which is only accessible from the backend

---

## Environment Variable Protection

### .env Files

Environment files containing secrets must never be committed to git.

**Verify `.gitignore` includes:**
```
.env
backend/.env
frontend/.env
```

**Verify secrets are not in version history:**
```bash
git log --all --oneline -- backend/.env
# Should return no results
```

### Secret Access Patterns

| Secret | Used By | How Accessed |
|--------|---------|-------------|
| `SUPABASE_SERVICE_KEY` | Backend only | `backend/.env` -> `config.py` -> `get_supabase_admin()` |
| `SUPABASE_ANON_KEY` | Backend + Frontend | `.env` files, embedded in frontend build |
| `SUPABASE_URL` | Backend + Frontend | `.env` files, embedded in frontend build |

### Production Secret Management

For production deployments:

1. **Fly.io:** Use `fly secrets set` to inject environment variables:
   ```bash
   fly secrets set SUPABASE_SERVICE_KEY="eyJ..."
   fly secrets set SUPABASE_ANON_KEY="eyJ..."
   fly secrets set SUPABASE_URL="https://..."
   ```

2. **Docker:** Pass secrets via environment variables in `docker-compose.yml` or `docker run -e`:
   ```yaml
   environment:
     - SUPABASE_SERVICE_KEY=${SUPABASE_SERVICE_KEY}
   ```

3. **Never** store secrets in:
   - Source code
   - Docker images (Dockerfile `ENV` or `ARG`)
   - Git commits
   - Frontend JavaScript bundles (except the anon key, which is public)

---

## Security Monitoring

### Supabase Dashboard

Monitor security events in the Supabase Dashboard:

- **Auth > Users:** View registered users, last sign-in times
- **Auth > Logs:** View authentication events (logins, failed attempts, token refreshes)
- **Database > Logs:** View query logs and errors (Pro plan)
- **Storage > Logs:** View file access patterns

### Audit Trail

The `lifecycle_history` table provides an audit trail for item state changes:

```sql
SELECT
  lh.changed_at,
  i.item_number,
  lh.old_state,
  lh.new_state,
  lh.old_revision,
  lh.new_revision,
  u.username as changed_by
FROM lifecycle_history lh
JOIN items i ON i.id = lh.item_id
LEFT JOIN users u ON u.id = lh.changed_by
ORDER BY lh.changed_at DESC
LIMIT 50;
```

### Advisors

Run security advisors via the Supabase Dashboard or MCP tools to check for:
- Tables without RLS enabled
- Missing indexes
- Unused indexes
- Other security recommendations

---

## Security Checklist

### Initial Setup

- [ ] Verify `backend/.env` is in `.gitignore`
- [ ] Verify `frontend/.env` is in `.gitignore`
- [ ] Verify service role key is not present in any frontend file
- [ ] Enable RLS on all public schema tables
- [ ] Create appropriate RLS policies for each table
- [ ] Configure CORS for production origins
- [ ] Set `CORS_ALLOW_ALL=false` for production
- [ ] Verify storage buckets are private (not public)
- [ ] Store a secure backup of API keys (see [21-BACKUP-RECOVERY-GUIDE.md](21-BACKUP-RECOVERY-GUIDE.md))

### Ongoing

- [ ] Review Supabase Auth logs for suspicious login activity monthly
- [ ] Verify no secrets have been committed to git
- [ ] Rotate API keys if team membership changes
- [ ] Review and update RLS policies when schema changes
- [ ] Keep backend dependencies updated (`pip install --upgrade`)
- [ ] Keep frontend dependencies updated (`npm update`)
- [ ] Review Supabase security advisors periodically

### Incident Response

If a security incident is suspected:

1. **Contain:** Rotate the compromised key immediately in Supabase Dashboard
2. **Assess:** Review Supabase Auth logs and database logs for unauthorized access
3. **Remediate:** Update all `.env` files, restart services, rebuild frontend
4. **Recover:** Restore from backup if data was modified (see [21-BACKUP-RECOVERY-GUIDE.md](21-BACKUP-RECOVERY-GUIDE.md))
5. **Document:** Record what happened, what was affected, and what was done to resolve it

---

## Security Resources

- **Supabase Security:** https://supabase.com/docs/guides/platform/going-into-prod
- **Supabase RLS:** https://supabase.com/docs/guides/database/postgres/row-level-security
- **FastAPI Security:** https://fastapi.tiangolo.com/tutorial/security/
- **OWASP Top 10:** https://owasp.org/www-project-top-ten/
- **Vue Security:** https://vuejs.org/guide/best-practices/security

---

**Last Updated:** 2025-01-29
**Version:** 3.0
**Related:** [23-SYSTEM-CONFIGURATION.md](23-SYSTEM-CONFIGURATION.md), [21-BACKUP-RECOVERY-GUIDE.md](21-BACKUP-RECOVERY-GUIDE.md)
