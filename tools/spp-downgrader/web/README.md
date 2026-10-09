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

Then open `http://localhost:8000` in your browser. Sign-in is disabled for localhost development.

## Deployment

Cloudflare Pages:

1. Connect the GitHub repository to Cloudflare Pages
2. Set build command: `python tools/spp-downgrader/web/build.py`
3. Set output directory: `tools/spp-downgrader/web/dist`
4. Set environment variable: `PYTHON_VERSION` = `3.12` (or later)

Configuration:

1. Create a Google OAuth 2.0 web client ID in [Google Cloud Console](https://console.cloud.google.com/)
2. Add your site URL as an authorized JavaScript origin
3. Paste the client ID into `web/config.js`

## Limitations

- .uspp files that contain raster fallbacks from the Painter plugin cannot be processed by the web version (these require lz4 and pyspng, which are unavailable in Pyodide). Use the desktop tool instead.
