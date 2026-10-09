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

Live at https://sdna-tools.msrk0320.workers.dev (Cloudflare Worker with static assets, config in `wrangler.jsonc`). Build and deploy:

```
python tools/spp-downgrader/web/build.py
cd tools/spp-downgrader/web && npx wrangler deploy
```

Access control: Cloudflare dashboard > Workers & Pages > sdna-tools > Settings > Domains & Routes > workers.dev > enable Cloudflare Access, then edit its policy in Zero Trust > Access > Applications:

1. The Access application covers `sdna-tools.msrk0320.workers.dev`
2. Set the Allow policy to include the emails of users who should have access
3. Users log in with a one-time code sent to their email
4. To invite someone, add their email to the policy; to remove access, delete it from the policy

## Limitations

- .uspp files that contain raster fallbacks from the Painter plugin cannot be processed by the web version (these require lz4 and pyspng, which are unavailable in Pyodide). Use the desktop tool instead.
