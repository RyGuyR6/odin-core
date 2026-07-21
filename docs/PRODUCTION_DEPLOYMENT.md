# Production Deployment — odincore.net

This document covers the complete domain cutover from the Render `.onrender.com`
URLs to the custom `odincore.net` domains.

---

## Service map

| Service | Render URL | Production domain |
|---|---|---|
| odin-web (Next.js frontend) | `odin-web-5uhp.onrender.com` | `odincore.net` |
| odin-web www redirect | `odin-web-5uhp.onrender.com` | `www.odincore.net` → redirect to `https://odincore.net` |
| odin-api (FastAPI backend) | `odin-api-63t2.onrender.com` | `api.odincore.net` |
| odin-mcp (MCP service) | `odin-mcp.onrender.com` | `mcp.odincore.net` |

---

## Render custom-domain setup

For each service:

1. Go to **Dashboard → [service] → Settings → Custom Domains**.
2. Click **Add Custom Domain** and enter the domain listed above.
3. Render will display the DNS record value you must add (see next section).
4. For `www.odincore.net` on `odin-web`, enable the **Redirect to `https://odincore.net`** toggle after adding the domain.

> Render auto-provisions a Let's Encrypt TLS certificate once DNS resolves.
> No manual certificate management is required.

---

## DNS records

Add the following records at your domain registrar.
**Use the exact values shown in the Render Custom Domains panel** — Render
displays the definitive IP or CNAME target for each service.  The table below
shows the record *types* and subdomain names; fill in the Render-provided
values for the `Value` column.

```
Type    Name    Value                               TTL
-----------------------------------------------------------
A/ALIAS @       <apex IP from Render dashboard>     300
CNAME   www     odin-web-5uhp.onrender.com          300
CNAME   api     odin-api-63t2.onrender.com          300
CNAME   mcp     odin-mcp.onrender.com               300
```

**Notes:**
- Render shows the required A-record IP (or recommends an ALIAS/ANAME record)
  in **Dashboard → odin-web → Settings → Custom Domains**.  Always use the
  value from the dashboard — do not copy an IP from external sources.
- If your registrar supports `ALIAS` / `ANAME` records, prefer
  `ALIAS @ odin-web-5uhp.onrender.com` for the apex instead of a bare A record.
- A TTL of 300 (5 minutes) allows fast iteration during cutover.
  Raise to `3600` once stable.

---

## Environment variables

Set these in **Render Dashboard → [service] → Environment**.

### odin-web (`odin-web-5uhp.onrender.com`)

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_ODIN_API_URL` | `https://api.odincore.net` |
| `ODIN_API_URL` | `https://api.odincore.net` |
| `ODIN_BACKEND_URL` | `https://api.odincore.net` |
| `NEXT_PUBLIC_ODIN_ENVIRONMENT` | `production` |
| `ODIN_WEB_ORIGIN` | `https://odincore.net` |

> `NEXT_PUBLIC_ODIN_API_URL` is embedded in browser JS at **build time**.
> After changing it, trigger a new deploy so it takes effect.

### odin-api (`odin-api-63t2.onrender.com`)

| Variable | Value |
|---|---|
| `ODIN_ENV` | `production` |
| `ODIN_AUTH_SECRET` | *(generate — see below)* |
| `ODIN_AUTH_SECURE_COOKIES` | `true` |
| `ODIN_AUTH_COOKIE_DOMAIN` | `.odincore.net` *(see note)* |
| `ODIN_MCP_URL` | `https://mcp.odincore.net` |
| `ODIN_MCP_HEALTH_URL` | `https://mcp.odincore.net/health` |

Generate a secret:

```sh
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'
```

> **`ODIN_AUTH_COOKIE_DOMAIN` note** — the frontend at `odincore.net` proxies
> all auth calls through `/api/auth/*`, so cookies are received by the browser
> as responses from `odincore.net`.  Without `ODIN_AUTH_COOKIE_DOMAIN` the
> cookie is scoped to `odincore.net` only, which is sufficient for the proxy
> architecture.  Set `ODIN_AUTH_COOKIE_DOMAIN=.odincore.net` (leading dot) only
> if you need the same cookie to be sent to `api.odincore.net` directly from the
> browser (e.g. for non-proxied API clients).  When in doubt, omit it.

### odin-mcp (`odin-mcp.onrender.com`)

| Variable | Value |
|---|---|
| `ODIN_ENV` | `production` |

---

## TLS / DNS propagation steps

1. Add DNS records at the registrar (TTL = 300).
2. In Render, add each custom domain and click **Verify**.
3. Wait 5–10 minutes for DNS to propagate (check with `dig api.odincore.net`
   or `nslookup api.odincore.net`).
4. In the Render dashboard, confirm **Certificate issued** on each domain.
5. Smoke-test each endpoint:
   ```sh
   curl -I https://odincore.net
   curl https://api.odincore.net/health
   curl https://mcp.odincore.net/health
   curl -I https://www.odincore.net       # expect 301/302 → odincore.net
   ```

---

## Rollback procedure

The `.onrender.com` URLs remain active at all times; no Render-side change is
needed to restore them.

1. In **Render → [service] → Custom Domains**: remove the custom domain entry.
2. Revert `odin-web` environment variables to the `.onrender.com` values:
   - `NEXT_PUBLIC_ODIN_API_URL=https://odin-api-63t2.onrender.com`
   - `ODIN_API_URL=https://odin-api-63t2.onrender.com`
   - `ODIN_BACKEND_URL=https://odin-api-63t2.onrender.com`
3. Trigger a new deploy on `odin-web` to rebuild with the reverted URLs.
4. Optionally remove or disable the DNS records at the registrar.

---

## Deployment verification checklist

- [ ] `https://odincore.net` — returns Odin web UI (HTTP 200)
- [ ] `https://www.odincore.net` — redirects (HTTP 301/302) to `https://odincore.net`
- [ ] `https://api.odincore.net/health` — returns `{"status":"ok"}` (HTTP 200)
- [ ] `https://mcp.odincore.net/health` — returns `{"status":"healthy"}` (HTTP 200)
- [ ] Login flow at `https://odincore.net/login` — sets `odin_access` cookie with
  `Domain=.odincore.net; Secure; HttpOnly`
- [ ] `https://odincore.net/api/auth/me` — returns 200 after login
- [ ] `https://api.odincore.net/api/mcp/status` — returns
  `{"api":"online","mcp":"online"}`
- [ ] TLS certificate valid in browser for all four domains
- [ ] Old `.onrender.com` URLs still respond (verify before removing from any
  internal bookmarks or client configs)
