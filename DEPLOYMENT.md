# Production Deployment

This project is prepared for a professional Cloudflare + Render deployment.

## Target Architecture

- Frontend: Cloudflare Pages
- Backend API: Render Web Service running `backend/Dockerfile`
- Database: Render Postgres with `pgvector`
- Prescription files: Cloudflare R2 once R2 is enabled
- DNS, SSL, CDN, WAF: Cloudflare
- Email: Resend
- AI: OpenRouter

Cloudflare Containers are still a valid future backend target, but this account currently does not have Cloudflare Containers access. Render is the deployable backend path now.

## Render Backend And Postgres

Create the production backend and database from `render.yaml`.

Render Blueprint URL:

```text
https://dashboard.render.com/blueprint/new?repo=https://github.com/72rs3/pharmacy-assistant
```

The Blueprint provisions:

- `pharmacy-assistant-api`: Docker web service from `backend/Dockerfile`
- `pharmacy-assistant-postgres`: PostgreSQL 16 database in Frankfurt

The backend service:

- Runs migrations before startup.
- Uses `/healthz` for health checks.
- Reads `DATABASE_URL` from the managed Render database.
- Prompts for real secrets in the Render Dashboard with `sync: false`.

Required values to fill in the Render Blueprint form:

```text
PHARMACY_ADMIN_EMAIL
PHARMACY_ADMIN_PASSWORD
OPENROUTER_API_KEY
R2_ACCOUNT_ID
R2_ENDPOINT_URL
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
RESEND_API_KEY
RESEND_FROM
```

Render will generate `SECRET_KEY` automatically.

Use PostgreSQL 16 or newer. Keep the database in `frankfurt` unless your users are mainly in another region. Use a paid database plan for point-in-time recovery and logical backups.

If you create the database manually instead of using the Blueprint, copy the external database URL and convert it to SQLAlchemy format:

```text
postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
```

The migration `backend/alembic/versions/4d5e6f708192_pgvector_rag_documents.py` enables `pgvector` with:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

## Cloudflare R2

Create an R2 bucket named:

```text
pharmacy-prescriptions
```

Create an R2 API token with read/write access to that bucket. Add these backend environment variables:

```text
PRESCRIPTION_STORAGE=r2
PRESCRIPTION_MAX_UPLOAD_BYTES=10485760
R2_ACCOUNT_ID=...
R2_ENDPOINT_URL=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=pharmacy-prescriptions
R2_REGION=auto
```

Prescription uploads are private by default. The backend downloads them from R2 only for approved pharmacy owners.

## Optional Future Cloudflare Backend

Deploying the backend as a Cloudflare Container from `backend/Dockerfile` requires Cloudflare Containers access on the account. The API currently reports that this requires the Workers Paid plan.

If Cloudflare Containers are enabled later, use the same backend environment variables currently defined in `render.yaml`:

```text
DATABASE_URL=...
DB_AUTO_CREATE=0
SECRET_KEY=...
CORS_ORIGINS=https://yourdomain.com,https://portal.yourdomain.com
CORS_ALLOW_ORIGIN_REGEX=^https://([a-z0-9-]+\.)?yourdomain\.com$
APP_PUBLIC_BASE_URL=https://yourdomain.com
OPENROUTER_API_KEY=...
RESEND_API_KEY=...
RESEND_FROM=Pharmacy <no-reply@yourdomain.com>
PRESCRIPTION_STORAGE=r2
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=pharmacy-prescriptions
```

The backend image runs migrations before starting the API:

```text
python -m alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port ${PORT:-9000}
```

Health check path:

```text
/healthz
```

## Cloudflare Frontend

Deploy `frontend` to Cloudflare Pages.

Cloudflare Pages project created:

```text
Project name: pharmacy-assistant-frontend
Preview URL: https://pharmacy-assistant-frontend.pages.dev
```

Build settings:

```text
Root directory: frontend
Build command: npm ci && npm run build
Build output directory: dist
```

Frontend environment variables:

```text
VITE_API_URL=https://api.yourdomain.com
VITE_PORTAL_HOSTS=portal.yourdomain.com
```

The files `frontend/public/_redirects` and `frontend/public/_headers` configure SPA routing and baseline security headers for Cloudflare Pages.

The file `frontend/wrangler.toml` sets the Cloudflare Pages project metadata and output directory for CLI-based deploys.

If the frontend ever needs to run as a container instead of Cloudflare Pages, use:

```text
frontend/Dockerfile.production
```

The default `frontend/Dockerfile` intentionally remains a development image because `docker-compose.yml` uses it for the local quick-start flow.

## DNS

Recommended records:

```text
yourdomain.com          -> Cloudflare Pages frontend
portal.yourdomain.com   -> Cloudflare Pages frontend
api.yourdomain.com      -> Cloudflare backend container
*.yourdomain.com        -> Cloudflare Pages frontend, if pharmacies use subdomains
```

For the current Render backend path, point `api.yourdomain.com` to the Render service custom domain instead of Cloudflare Containers.

If pharmacy storefronts use subdomains, set each pharmacy `domain` to the subdomain label or hostname expected by the app.

## Launch Checklist

- Replace all placeholder secrets.
- Use a strong `SECRET_KEY`.
- Create the first admin with a strong temporary password, then rotate it.
- Confirm Render backups are enabled.
- Enable R2 in the Cloudflare dashboard, then confirm upload/download works through the owner portal.
- Confirm CORS only allows production domains.
- Confirm `/healthz` returns `{"ok": true}`.
- Run migrations against production.
- Run the test suite before deploying.
- Run the frontend build with `npm ci && npm run build` from `frontend/`.
- Add Cloudflare WAF/rate limiting rules for `/auth/*`, `/ai/*`, `/contact`, and prescription upload routes.

## Current Local Verification Note

Backend tests pass locally. Frontend install/build now also passes locally.

Verified commands:

```text
python -m pytest backend\tests
npm ci --no-audit --no-fund
npm run build
npm run lint
```

`npm run lint` exits successfully with warnings only. The warnings are existing hook dependency/style warnings, not deployment blockers.

## Current Live Platform Status

Cloudflare:

- Pages project `pharmacy-assistant-frontend` was created.
- Pages URL: `https://pharmacy-assistant-frontend.pages.dev`
- R2 bucket creation is blocked until R2 is enabled once in the Cloudflare dashboard.
- Cloudflare Containers are blocked until the account is upgraded to Workers Paid. The API returned: `Unauthorized: You do not have access to Cloudflare Containers. Deploying containers requires the Workers Paid plan.`
- GitHub source connection is blocked by Cloudflare Pages Git installation error `8000011`. Reinstall or repair the Cloudflare Pages GitHub app integration, then reconnect `72rs3/pharmacy-assistant`.
- Wrangler deploy from this local shell requires `CLOUDFLARE_API_TOKEN`.

Render:

- `render.yaml` is ready for the managed Postgres database and backend API service.
- No `RENDER_API_KEY` / `RENDER_API_TOKEN` was present locally, and no callable Render deployment tools were exposed in this session.

Docker:

- Docker Desktop is installed but the Linux engine is not running locally, so image build verification could not run on this machine.

After Cloudflare R2 is enabled and tokens/integrations are available, use:

```text
npm ci && npm run build
npx wrangler pages deploy dist --project-name pharmacy-assistant-frontend --branch main --commit-dirty=true
```
