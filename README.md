# Pharmacy Assistant

AI‑powered pharmacy assistant with a customer storefront, owner portal, pharmacist escalation, and a database‑backed cart.

## Highlights
- Multi‑tenant storefronts (per‑pharmacy domain like `sunrise.localhost`).
- Owner portal for inventory, products, orders, appointments, escalations.
- AI chat with safety triage, deterministic medicine/product lookup, and escalation.
- RAG search with pgvector (optional) and document ingestion.
- Persistent cart (server‑side) tied to customer session.

## Quick Start (Docker)
1) Copy environment template:
```bash
copy .env.example .env
```
2) Set required values in `.env`:
   - `OPENROUTER_API_KEY` (AI)
   - `PHARMACY_ADMIN_EMAIL` / `PHARMACY_ADMIN_PASSWORD` (optional bootstrap)
3) Start services:
```bash
docker compose up -d --build
```
4) Run migrations:
```bash
docker compose exec backend alembic upgrade head
```

### URLs
- Customer storefront: `http://{pharmacy}.localhost:5173`
- Owner portal: `http://localhost:5173/portal/login`
- Backend API: `http://localhost:9000`

## Configuration
Primary settings live in `.env` (used by Docker Compose).

Important keys:
- `OPENROUTER_API_KEY` and model settings (AI)
- `BACKEND_PORT`, `FRONTEND_PORT`
- `POSTGRES_*` (database)
- `PHARMACY_ADMIN_EMAIL/PASSWORD` (optional bootstrap admin)
- `VITE_PORTAL_HOSTS` (domains treated as portal)

If you run the frontend outside Docker, you can set:
```
VITE_API_URL=http://localhost:9000
```

## Database + Admin Tools
Optional pgAdmin:
```bash
docker compose --profile tools up -d
```
Then open `http://localhost:5050`.

## Common Commands
- Rebuild backend:
```bash
docker compose up -d --build backend
```
- Rebuild frontend:
```bash
docker compose up -d --build frontend
```
- View logs:
```bash
docker compose logs --tail=200 backend
```

## Notes
- Cart is persisted in the database by `session_id`.
- AI responses are constrained by tool output to avoid hallucinations.
- For subdomain testing (`sunrise.localhost`), ensure your browser accepts `.localhost`.

## License
Private/internal project. Add a license if you intend to distribute.
