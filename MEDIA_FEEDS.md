# Media feeds

## Instagram

The public post thumbnails and links for `@kispride`, `@kis_athletics`, and
`@kisstuco` are stored as a manual snapshot in `assets/media.js` and
`assets/insta/`. Refreshes from Instagram's API are deferred until the school
approves access.

## YouTube

The latest saved channel videos are displayed from `assets/media.js`. Live API
updates are deferred until a Google Cloud project and YouTube Data API key can
be created. One server-side API key will serve both public channels; it should
be stored in Vercel as `YOUTUBE_API_KEY`, never in client-side files.
