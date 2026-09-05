# Free Docker Demo Deployment

This deployment keeps the public app Docker-based by building one container that serves both:

- the React frontend from `frontend/`
- the FastAPI backend from `backend/`

The demo container uses `Dockerfile.demo` and the Render Blueprint in `render.yaml`.

## Architecture

- App hosting: Render Free Web Service
- Runtime: Docker
- Database: SQLite inside the demo container by default
- Public URL: `https://pharmacy-assistant-demo.onrender.com`, unless Render changes the service slug
- File uploads: local container storage for demo only

Render Free services sleep after inactivity, so the first request can take about a minute to wake up.
The demo database and local uploads are ephemeral on free Render services and can disappear after redeploys or restarts.

## 1. Optional: Create A Free Supabase Database

The default free demo uses SQLite inside the Render container so there is no external database setup.

For a longer-lived demo, create a Supabase project and add `DATABASE_URL` to Render.

1. Create a Supabase project.
2. Open Project Settings, then Database.
3. Copy the connection string.
4. Convert it to SQLAlchemy psycopg format if needed:

```text
postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres?sslmode=require
```

Supabase supports Postgres extensions. If the vector migration fails, enable the `vector` extension in Supabase SQL editor:

```sql
create extension if not exists vector;
```

## 2. Push This Repo To GitHub

Render Blueprints read `render.yaml` from GitHub/GitLab/Bitbucket.

```bash
git add Dockerfile.demo backend/app/main.py render.yaml DEMO_DEPLOYMENT.md
git commit -m "Add free Docker demo deployment"
git push origin main
```

## 3. Deploy On Render

Open this Blueprint URL after the changes are pushed:

```text
https://dashboard.render.com/blueprint/new?repo=https://github.com/72rs3/pharmacy-assistant
```

Fill these required secret values in Render:

```text
PHARMACY_ADMIN_EMAIL
PHARMACY_ADMIN_PASSWORD
OPENROUTER_API_KEY
```

Optional email values:

```text
RESEND_API_KEY
RESEND_FROM
```

For a demo, `PRESCRIPTION_STORAGE=local` is already set in `render.yaml`, so Cloudflare R2 is not required.

## 4. Verify

After Render says the service is live:

```text
https://pharmacy-assistant-demo.onrender.com/healthz
```

Expected response:

```json
{"ok":true}
```

Then open:

```text
https://pharmacy-assistant-demo.onrender.com
```

## 5. Use On CV And GitHub

```text
Live demo: https://pharmacy-assistant-demo.onrender.com
Source code: https://github.com/72rs3/pharmacy-assistant
```

If Render gives the service a different URL, use that URL instead.
