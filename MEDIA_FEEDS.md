# Media feeds

## Instagram

The public post thumbnails and links for `@kispride`, `@kis_athletics`, and
`@kisstuco` are stored as a snapshot in `assets/media.js` and
`assets/insta/`. KIS has not provided Instagram API access, so the snapshot is
refreshed without the API:

1. A daily scheduled task (06:33 KST) reads each account's public profile and
   post pages in a browser and commits `assets/instagram_queue.json` (through
   the GitHub web editor) with the latest six posts per account (code, date,
   caption, video flag, thumbnail URL).
2. The push triggers `.github/workflows/sync-instagram.yml`, which runs
   `sync_instagram.py`: it downloads new thumbnails into `assets/insta/`,
   rewrites the `instagram` section of `assets/media.js`, removes thumbnails no
   longer shown, deletes the queue file and commits. Vercel redeploys on that
   commit.

The accounts shown are the `renderIG(...)` calls in `index.html`; to add an
account, add its widget there and the next daily run picks it up.

## YouTube

When configured, the page requests the six latest public uploads for both
channels from `/api/youtube`. The Vercel function uses a server-side
`YOUTUBE_API_KEY`; it is never sent to the browser. Responses are cached for
one minute, open pages re-check every five minutes, and the saved
`assets/media.js` videos remain as a fallback.

Enable **YouTube Data API v3** in the Google Cloud project, create a key
restricted to that API, and add it to the Vercel project's Production
environment as `YOUTUBE_API_KEY`. Redeploy after setting the variable.
