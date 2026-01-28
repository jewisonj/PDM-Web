# PDM-Web Deployment Guide

Deploy PDM-Web to Fly.io as a single container serving both the FastAPI backend and Vue frontend.

## Prerequisites

1. **Fly.io CLI** - Install from https://fly.io/docs/hands-on/install-flyctl/
2. **Fly.io Account** - Sign up at https://fly.io
3. **Supabase Project** - Your database and auth provider

## Quick Deploy

### 1. Login to Fly.io

```bash
fly auth login
```

### 2. Create the App (First Time Only)

```bash
cd J:\PDM-Web
fly apps create pdm-web
```

### 3. Set Backend Secrets

These are runtime environment variables for the FastAPI backend:

```bash
fly secrets set SUPABASE_URL=https://your-project.supabase.co
fly secrets set SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
fly secrets set SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### 4. Deploy

Deploy with frontend build args (Vite needs these at build time):

```bash
fly deploy \
  --build-arg VITE_SUPABASE_URL=https://your-project.supabase.co \
  --build-arg VITE_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### 5. Open Your App

```bash
fly open
```

Your app will be available at: `https://pdm-web.fly.dev`

---

## Deploy Script (Recommended)

Create a `deploy.ps1` script for convenience:

```powershell
# deploy.ps1 - PDM-Web Deployment Script
$SUPABASE_URL = "https://your-project.supabase.co"
$SUPABASE_ANON_KEY = "eyJ..."

fly deploy `
  --build-arg VITE_SUPABASE_URL=$SUPABASE_URL `
  --build-arg VITE_SUPABASE_ANON_KEY=$SUPABASE_ANON_KEY
```

Then just run: `.\deploy.ps1`

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  Fly.io                         │
│  ┌───────────────────────────────────────────┐  │
│  │           PDM-Web Container               │  │
│  │                                           │  │
│  │   ┌─────────────────────────────────────┐ │  │
│  │   │  FastAPI (Python)                   │ │  │
│  │   │  - /api/* routes                    │ │  │
│  │   │  - /health endpoint                 │ │  │
│  │   │  - Serves static files              │ │  │
│  │   └─────────────────────────────────────┘ │  │
│  │                    │                      │  │
│  │   ┌─────────────────────────────────────┐ │  │
│  │   │  Vue Frontend (Static Files)        │ │  │
│  │   │  - Built during Docker build        │ │  │
│  │   │  - Served from /static directory    │ │  │
│  │   └─────────────────────────────────────┘ │  │
│  │                                           │  │
│  └───────────────────────────────────────────┘  │
│                        │                        │
└────────────────────────│────────────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │      Supabase        │
              │  - PostgreSQL DB     │
              │  - Auth              │
              │  - Storage           │
              └──────────────────────┘
```

---

## Environment Variables

### Backend (Runtime Secrets)

| Variable | Description | Required |
|----------|-------------|----------|
| `SUPABASE_URL` | Supabase project URL | Yes |
| `SUPABASE_ANON_KEY` | Supabase anonymous/public key | Yes |
| `SUPABASE_SERVICE_KEY` | Supabase service role key | Yes |
| `DEBUG` | Enable debug mode (default: false) | No |
| `CORS_ALLOW_ALL` | Allow all CORS origins (default: false) | No |

### Frontend (Build Args)

| Variable | Description | Required |
|----------|-------------|----------|
| `VITE_SUPABASE_URL` | Supabase project URL | Yes |
| `VITE_SUPABASE_ANON_KEY` | Supabase anonymous/public key | Yes |

---

## Useful Commands

```bash
# View logs
fly logs

# SSH into the container
fly ssh console

# Check app status
fly status

# Scale resources
fly scale memory 1024  # Increase to 1GB RAM
fly scale count 2      # Run 2 instances

# View secrets (names only)
fly secrets list

# Restart the app
fly apps restart pdm-web

# View deployment history
fly releases
```

---

## Troubleshooting

### Build Fails

1. Check Docker build locally first:
   ```bash
   docker build -t pdm-web-test \
     --build-arg VITE_SUPABASE_URL=https://test.supabase.co \
     --build-arg VITE_SUPABASE_ANON_KEY=test .
   ```

2. View build logs on Fly.io:
   ```bash
   fly logs --instance <instance-id>
   ```

### App Won't Start

1. Check health endpoint:
   ```bash
   curl https://pdm-web.fly.dev/health
   ```

2. View application logs:
   ```bash
   fly logs
   ```

3. Verify secrets are set:
   ```bash
   fly secrets list
   ```

### Database Connection Issues

1. Verify Supabase URL is correct
2. Check that service key has proper permissions
3. Test connection from Fly.io SSH:
   ```bash
   fly ssh console
   curl $SUPABASE_URL/rest/v1/items -H "apikey: $SUPABASE_ANON_KEY"
   ```

---

## Updating the App

Just run the deploy command again:

```bash
fly deploy \
  --build-arg VITE_SUPABASE_URL=https://your-project.supabase.co \
  --build-arg VITE_SUPABASE_ANON_KEY=eyJ...
```

Fly.io will:
1. Build a new Docker image
2. Deploy it with zero-downtime rolling update
3. Health check the new instance
4. Route traffic to the new instance

---

## Cost Estimate

With the default configuration (`fly.toml`):
- **VM**: shared-cpu-1x, 512MB RAM
- **Auto-stop**: Enabled (stops when no traffic)
- **Estimated cost**: ~$0-5/month for low traffic

See https://fly.io/docs/about/pricing/ for current pricing.
