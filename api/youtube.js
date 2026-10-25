const CHANNELS = {
  kispride: "UCb0vJLXOLeTzO-1BH-vwM9g",
  livestream: "UC_pnYI1H8Zbct0gP684S1Qg",
};

async function getLatest(channelId, apiKey) {
  // A channel's uploads playlist ID is its channel ID with C changed to U.
  const uploadsId = `${channelId[0]}U${channelId.slice(2)}`;
  const url = new URL("https://www.googleapis.com/youtube/v3/playlistItems");
  url.search = new URLSearchParams({
    part: "snippet",
    playlistId: uploadsId,
    maxResults: "6",
  });

  const response = await fetch(url, {
    headers: { "X-Goog-Api-Key": apiKey },
  });
  if (!response.ok) {
    throw new Error(`YouTube API returned HTTP ${response.status}`);
  }

  const payload = await response.json();
  return (payload.items || []).flatMap(({ snippet = {} }) => {
    const id = snippet.resourceId?.videoId;
    return id ? [{
      id,
      title: snippet.title || "",
      published: (snippet.publishedAt || "").slice(0, 10),
    }] : [];
  });
}

export default async function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET");
    return res.status(405).json({ error: "Method not allowed" });
  }

  const apiKey = process.env.YOUTUBE_API_KEY;
  if (!apiKey) {
    return res.status(503).json({ error: "YouTube API is not configured" });
  }

  try {
    const entries = await Promise.all(
      Object.entries(CHANNELS).map(async ([name, channelId]) => [
        name,
        await getLatest(channelId, apiKey),
      ]),
    );
    res.setHeader("Cache-Control", "public, s-maxage=60, stale-while-revalidate=300");
    return res.status(200).json({
      updatedAt: new Date().toISOString(),
      videos: Object.fromEntries(entries),
    });
  } catch {
    return res.status(502).json({ error: "Could not refresh YouTube channels" });
  }
}
