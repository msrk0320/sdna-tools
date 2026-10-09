# SPP Downgrader Web

A browser-based Substance Painter project downgrader built with Pyodide 0.27.7.

## Build

```
python tools/spp-downgrader/web/build.py
```

This creates `tools/spp-downgrader/web/dist/` with all required files and the packaged engine.

## Local Testing

```
python -m http.server 8000 -d tools/spp-downgrader/web/dist
```

Then open `http://localhost:8000` in your browser.

## Deployment

Build and deploy to Cloudflare Pages:

```
python tools/spp-downgrader/web/build.py
npx wrangler pages deploy tools/spp-downgrader/web/dist --project-name sdna-tools --branch main
```

Access control is managed via Cloudflare Zero Trust > Access > Applications:

1. Create a Self-hosted application with domain `sdna-tools.pages.dev` (and `*.sdna-tools.pages.dev` for preview URLs)
2. Add an Allow policy that includes emails of users who should have access
3. Users log in with a one-time code sent to their email
4. To invite someone, add their email to the policy; to remove access, delete it from the policy

## Limitations

- .uspp files that contain raster fallbacks from the Painter plugin cannot be processed by the web version (these require lz4 and pyspng, which are unavailable in Pyodide). Use the desktop tool instead.
