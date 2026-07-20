# Odin Web

Odin's remote control center.

## Local development

```bash
cp .env.example .env.local
npm install
npm run dev
```

Open http://localhost:3000.

## Validation

```bash
npm run verify
```

## Production

The application is configured for a standalone Next.js build and includes a multi-stage Dockerfile.

## OW-002 application shell

OW-002 adds responsive desktop/mobile navigation and a same-origin health proxy at `/api/odin/health`.

Configure the backend in `.env.local`:

```bash
ODIN_API_URL=http://localhost:8000
NEXT_PUBLIC_ODIN_API_URL=http://localhost:8000
```

The proxy tries `/health`, `/api/health`, and `/runtime/health` by default. Override these with `ODIN_HEALTH_PATHS` when necessary.
