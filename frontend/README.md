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
