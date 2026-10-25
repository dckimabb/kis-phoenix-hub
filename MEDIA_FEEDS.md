# Media feeds

## Instagram

The public post thumbnails and links for `@kispride`, `@kis_athletics`, and
`@kisstuco` are stored as a manual snapshot in `assets/media.js` and
`assets/insta/`. Refreshes from Instagram's API are deferred until the school
approves access.

## YouTube

When configured, the page requests the six latest public uploads for both
channels from `/api/youtube`. The Vercel function uses a server-side
`YOUTUBE_API_KEY`; it is never sent to the browser. Responses are cached for
one minute, open pages re-check every five minutes, and the saved
`assets/media.js` videos remain as a fallback.

Enable **YouTube Data API v3** in the Google Cloud project, create a key
restricted to that API, and add it to the Vercel project's Production
environment as `YOUTUBE_API_KEY`. Redeploy after setting the variable.
