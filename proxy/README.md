# NDAP CORS proxy

NDAP's `/v1/openapi` endpoint does not send `Access-Control-Allow-Origin`, so a
browser cannot read its responses directly. This Worker is a tiny, stateless
forwarder that only proxies GET requests to `loadqa.ndapapi.com` and adds CORS
headers, so the static GitHub Pages demo can fetch dataset rows client-side.

It stores no secrets and no data. The browser builds the full NDAP URL from the
recipe shipped in `docs/assets/ndap_recipes.json` and passes it as `?url=...`.

## Deploy (free Cloudflare account)

```bash
cd proxy
npx wrangler login      # one-time, opens browser
npx wrangler deploy
```

Wrangler prints a URL like `https://ndap-cors-proxy.<your-subdomain>.workers.dev`.
Paste that into the demo's Settings → "Data proxy URL".

## Test

```bash
# replace <PROXY> with your workers.dev URL
NDAP="https://loadqa.ndapapi.com/v1/openapi?API_Key=...&ind=...&dim=...&pageno=1"
curl -s "<PROXY>/?url=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$NDAP")" | head -c 300
```

## Notes

- The proxy is host-locked: it refuses to forward to anything other than
  `loadqa.ndapapi.com`, so it can't be used as an open relay.
- For a friends demo it allows any origin (`*`). To lock it to your Pages site,
  replace the `Access-Control-Allow-Origin` value in `worker.js`.
