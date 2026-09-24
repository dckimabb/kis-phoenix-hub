#!/usr/bin/env python3
"""Snapshot KIS Instagram + YouTube + admissions news + upcoming events
into assets/media.js.

Instagram CDN image URLs are signed and expire, so post thumbnails are
downloaded into assets/insta/. YouTube thumbnails hotlink from i.ytimg.com
(stable). Upcoming events are parsed from the server-rendered calendar on
kis.or.kr/academics/high-school. Re-run this script any time to refresh.

Usage: python3 refresh_media.py
"""
import json, os, re, subprocess, time

BASE = os.path.dirname(os.path.abspath(__file__))
INSTA_DIR = os.path.join(BASE, "assets", "insta")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126 Safari/537.36")

IG_USERS = ["kispride", "kis_athletics", "kisstuco"]
YT_CHANNELS = [
    ("kispride", "UCb0vJLXOLeTzO-1BH-vwM9g"),      # KIS Pride
    ("livestream", "UC_pnYI1H8Zbct0gP684S1Qg"),    # KIS Livestream
]
EVENTS_PAGE = "https://www.kis.or.kr/academics/high-school"
EVENTS_ELEMENT = "19287"  # fsEl_19287 = HS Upcoming Events calendar slideshow
N_POSTS = 6
N_VIDEOS = 6


def get(url, headers=None):
    # curl avoids the missing-CA-bundle issue in framework Python builds
    cmd = ["curl", "-sfL", "--http1.1", "--max-time", "30", "-A", UA]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    cmd.append(url)
    for attempt in range(4):
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode == 0:
            return r.stdout
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"curl failed ({r.returncode}) for {url}")


IG_APP_ID = {"x-ig-app-id": "936619743392459"}


def get_ig(url):
    # Instagram resets plain-curl TLS fingerprints; curl_cffi impersonation
    # is required for the API endpoints (CDN image downloads are fine via curl)
    from curl_cffi import requests as cffi_requests
    resp = cffi_requests.get(url, headers=IG_APP_ID, impersonate="safari", timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:80]}")
    return resp.content


def _save_post(ig_user, code, img_url, is_video, caption):
    fname = f"{ig_user}_{code}.jpg"
    with open(os.path.join(INSTA_DIR, fname), "wb") as f:
        f.write(get(img_url))
    print(f"  IG {code} saved")
    return {"code": code, "img": f"assets/insta/{fname}",
            "video": is_video, "caption": (caption or "")[:120]}


def _ig_via_profile_api(ig_user):
    url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={ig_user}"
    user = json.loads(get_ig(url))["data"]["user"]
    posts = []
    for e in user["edge_owner_to_timeline_media"]["edges"][:N_POSTS]:
        n = e["node"]
        cap = n.get("edge_media_to_caption", {}).get("edges", [])
        posts.append(_save_post(ig_user, n["shortcode"], n["display_url"],
                                n.get("is_video", False),
                                cap[0]["node"]["text"] if cap else ""))
    return {"followers": user["edge_followed_by"]["count"], "posts": posts}


IG_KNOWN_IDS = {}


def _ig_via_feed_api(ig_user):
    # Fallback for accounts where web_profile_info 400s: resolve the numeric
    # id, then use the public feed endpoint.
    uid = IG_KNOWN_IDS.get(ig_user)
    if not uid:
        # try plain curl first, then curl_cffi impersonation (login-wall bypass)
        html = get(f"https://www.instagram.com/{ig_user}/").decode("utf-8", "replace")
        m = re.search(r'"profile_id":"(\d+)"', html) or re.search(r"profilePage_(\d+)", html)
        if not m:
            html = get_ig(f"https://www.instagram.com/{ig_user}/").decode("utf-8", "replace")
            m = re.search(r'"profile_id":"(\d+)"', html) or re.search(r"profilePage_(\d+)", html)
        if not m:
            raise RuntimeError("could not resolve profile id")
        uid = m.group(1)
    data = json.loads(get_ig(f"https://i.instagram.com/api/v1/feed/user/{uid}/?count=12"))
    posts = []
    for item in data.get("items", [])[:N_POSTS]:
        media = item.get("carousel_media", [item])[0]
        candidates = media.get("image_versions2", {}).get("candidates", [])
        if not candidates:
            continue
        caption = (item.get("caption") or {}).get("text", "")
        posts.append(_save_post(ig_user, item["code"], candidates[0]["url"],
                                item.get("media_type") == 2, caption))
    if not posts:
        raise RuntimeError("feed endpoint returned no renderable items")
    return {"followers": None, "posts": posts}


def fetch_instagram(ig_user):
    os.makedirs(INSTA_DIR, exist_ok=True)
    first, second = ((_ig_via_feed_api, _ig_via_profile_api)
                     if ig_user in IG_KNOWN_IDS
                     else (_ig_via_profile_api, _ig_via_feed_api))
    try:
        return first(ig_user)
    except Exception as ex:
        print(f"  {first.__name__} failed ({ex}); trying {second.__name__}")
        return second(ig_user)


def fetch_youtube(channel_id):
    xml = get(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}").decode()
    entries = re.findall(
        r"<entry>.*?<yt:videoId>([^<]+)</yt:videoId>.*?<title>([^<]+)</title>"
        r".*?<published>([^<]+)</published>", xml, re.S)
    videos = [{"id": vid, "title": _unescape(title), "published": pub[:10]}
              for vid, title, pub in entries[:N_VIDEOS]]
    for v in videos:
        print(f"  YT {v['id']} {v['title'][:50]}")
    return videos


import urllib.parse
from email.utils import parsedate_to_datetime

ADMISSIONS_OUTLETS = [
    # (display name, tag, google-news query, expected " - Suffix" on titles)
    ("Inside Higher Ed", "IHE", 'admissions source:"Inside Higher Ed" when:90d', "Inside Higher Ed"),
    ("Forbes", "Forbes", 'college source:Forbes when:90d', "Forbes"),
    ("U.S. News", "USN", 'college source:"U.S. News & World Report" when:90d', "U.S. News & World Report"),
    ("Niche", "Niche", 'college source:Niche when:365d', "Niche"),
]


def _unescape(s):
    import html as _html
    return _html.unescape(re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s, flags=re.S)).strip()


def _items(xml):
    return re.findall(r"<item>(.*?)</item>", xml, re.S)


def _field(item, tag):
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", item, re.S)
    return _unescape(m.group(1)) if m else ""


def fetch_admissions():
    articles = []
    for name, tag, query, suffix in ADMISSIONS_OUTLETS:
        url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(query)
               + "&hl=en-US&gl=US&ceid=US:en")
        # Google News RSS intermittently returns a valid-but-empty feed; retry
        items = []
        for attempt in range(5):
            try:
                items = _items(get(url).decode("utf-8", "replace"))
            except Exception as ex:
                print(f"  admissions {name} fetch error: {ex}")
            if items:
                break
            time.sleep(4)
        kept = 0
        for item in items:
            title = _field(item, "title")
            if not title.endswith(" - " + suffix):
                continue  # Google News mixes in other outlets; keep exact matches only
            title = title[: -len(" - " + suffix)]
            try:
                dt = parsedate_to_datetime(_field(item, "pubDate"))
            except Exception:
                continue
            articles.append({"outlet": name, "tag": tag, "title": title,
                             "url": _field(item, "link"), "date": dt.strftime("%Y-%m-%d"),
                             "_ts": dt.timestamp()})
            kept += 1
            if kept >= 3:
                break
        print(f"  admissions {name}: {kept} articles")
    articles.sort(key=lambda a: -a["_ts"])
    for a in articles:
        a.pop("_ts")
    return articles


def fetch_events():
    html = get(EVENTS_PAGE).decode("utf-8", "replace")
    # Server-rendered calendar slideshow: <article aria-labelledby="fsArticle_19287_...">
    arts = re.findall(
        rf'<article aria-labelledby="fsArticle_{EVENTS_ELEMENT}_\d+"\s*>(.*?)</article>',
        html, re.S)
    events = []
    for a in arts:
        m = re.search(r'<time datetime="([^"]+)" class="fsDate"', a)
        t = re.search(r'<div class="fsTitle"[^>]*>(.*?)</div>', a, re.S)
        if not m or not t:
            continue
        title = _unescape(re.sub(r"<[^>]+>", "", t.group(1)))
        start = re.search(r'<time datetime="([^"]+)" class="fsStartTime"', a)
        end = re.search(r'<time datetime="([^"]+)" class="fsEndTime"', a)
        desc = re.search(r'<div class="fsDescription">(.*?)</div>', a, re.S)
        location = ""
        if desc:
            dtext = _unescape(re.sub(r"<br\s*/?>", "\n", desc.group(1)))
            lm = re.search(r"Location:\s*(.+)", dtext)
            if lm:
                location = lm.group(1).strip()
        events.append({
            "date": m.group(1)[:10],
            "title": title,
            "start": start.group(1)[11:16] if start else "",
            "end": end.group(1)[11:16] if end else "",
            "location": location,
        })
        print(f"  event {events[-1]['date']} {title[:50]}")
    return events


NEWS_PAGE = "https://www.kis.or.kr/5tund3nt5-kis-news"
NEWS_ELEMENT = "23479"  # fsEl_23479 = High School News post list (Elem 23470, Middle 23474)
N_NEWS = 6


def fetch_kis_news():
    """High School News posts from the KIS news page.

    The page renders its post lists via AJAX; /fs/elements/{id} returns the
    HTML fragment for one list. Post dates only exist on each post's own
    page (article:published meta), so every post is fetched once."""
    frag = get(f"https://www.kis.or.kr/fs/elements/{NEWS_ELEMENT}").decode("utf-8", "replace")
    posts = []
    for art in re.split(r"<article\b", frag)[1:]:
        t = re.search(r'<div class="fsTitle[^"]*"[^>]*>\s*<a class="fsPostLink"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                      art, re.S)
        if not t:
            continue
        url = t.group(1)
        title = _unescape(re.sub(r"<[^>]+>", "", t.group(2)))
        thumb = ""
        sizes = re.search(r'data-image-sizes="([^"]+)"', art)
        if sizes:
            try:
                arr = json.loads(_unescape(sizes.group(1)))
                thumb = ({d["width"]: d["url"] for d in arr}.get(512) or arr[0]["url"])
            except Exception:
                pass
        date = ""
        try:
            page = get(url).decode("utf-8", "replace")
            dm = re.search(r'property="article:published" content="(\d{4}-\d{2}-\d{2})', page)
            if dm:
                date = dm.group(1)
        except Exception:
            pass
        posts.append({"title": title, "url": url, "thumb": thumb, "date": date})
        print(f"  news {date or '????-??-??'} {title[:55]}")
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts[:N_NEWS]


PARENT_RESOURCES = "https://www.kis.or.kr/parent-resources"
CAL_PAGE = "https://www.kis.or.kr/connect/school-calendar"


def fetch_community():
    """Parse the school/community calendar month grid (server-rendered)."""
    html = get(CAL_PAGE).decode("utf-8", "replace")
    events = []
    for box in re.split(r'<div class="fsCalendarDaybox', html)[1:]:
        d = re.search(r'<div class="fsCalendarDate" data-day="(\d+)" data-year="(\d+)" data-month="(\d+)"', box)
        if not d:
            continue
        day, year, month0 = map(int, d.groups())
        date = f"{year:04d}-{month0 + 1:02d}-{day:02d}"  # data-month is 0-indexed
        for info in re.findall(r'<div class="fsCalendarInfo">(.*?)</div>', box, re.S):
            title = re.search(r'<a class="fsCalendarEventTitle[^"]*"[^>]*>([^<]+)</a>', info)
            if not title:
                continue
            cal = re.search(r"title='([^']+)'", info)
            color = re.search(r"background:(#[0-9A-Fa-f]{3,6})", info)
            start = re.search(r'<time datetime="[^"]*T(\d{2}:\d{2})[^"]*" class="fsStartTime"', info)
            events.append({
                "date": date,
                "title": _unescape(title.group(1)),
                "cal": cal.group(1) if cal else "",
                "color": color.group(1) if color else "#44576B",
                "start": start.group(1) if start else "",
            })
    events.sort(key=lambda e: (e["date"], e["start"]))
    print(f"  community: {len(events)} events in current month grid")
    return events


def _anchor_href(html, label):
    """Href of the first <a> whose inner text contains label."""
    m = re.search(r'<a\b[^>]*href="([^"#][^"]*)"[^>]*>(?:(?!</a>).){0,300}?' + re.escape(label),
                  html, re.S | re.I)
    return m.group(1) if m else None


def fetch_lunch():
    """Discover the current lunch-menu PDF on the parent-resources page and
    parse it into per-day menus. The school replaces the PDF (new finalsite
    URL) every month/update, so this re-resolves the link each run."""
    html = get(PARENT_RESOURCES).decode("utf-8", "replace")
    links = {
        "lunch": _anchor_href(html, "Lunch Menus"),
        "schoolProfile": _anchor_href(html, "School Profile"),
        "accessPass": _anchor_href(html, "Access Pass") or _anchor_href(html, "ACCESS PASS"),
    }
    pdf_url = links["lunch"]
    if not pdf_url:
        raise RuntimeError("no Lunch Menus link found on parent-resources")
    print(f"  lunch PDF: {pdf_url}")
    pdf_path = os.path.join(BASE, "assets", "lunch_menu.pdf")
    with open(pdf_path, "wb") as f:
        f.write(get(pdf_url))

    import pdfplumber
    days = {}
    label = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            if not label:
                m = re.search(r"([A-Z][a-z]+ Menu)", " ".join(w["text"] for w in words[:12]))
                if m:
                    label = m.group(1)
            # date headers appear as 2026-08-10 (Aug PDF) or 9/1/26 (Sep PDF)
            def _norm_date(t):
                m = re.fullmatch(r"\d{4}-\d{2}-\d{2}", t)
                if m:
                    return t
                m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", t)
                if m:
                    mo, dd, yy = map(int, m.groups())
                    yy += 2000 if yy < 100 else 0
                    return f"{yy:04d}-{mo:02d}-{dd:02d}"
                return None
            dates = [w for w in words if _norm_date(w["text"])]
            if len(dates) < 2:
                continue
            dates.sort(key=lambda w: w["x0"])
            centers = [(w["x0"] + w["x1"]) / 2 for w in dates]
            bounds = [0] + [(centers[i] + centers[i + 1]) / 2 for i in range(len(centers) - 1)] + [page.width]
            # left-margin content boundary: nothing left of first column's start
            left_edge = min(w["x0"] for w in dates) - 10
            date_bottom = max(w["bottom"] for w in dates)
            # section labels sit in the left margin
            sec_words = [w for w in words if w["x1"] < left_edge and re.search(r"[A-Za-z]", w["text"])]
            intl_lbl = next((w for w in sec_words if w["text"].lower().startswith("international")), None)
            kor = next((w for w in sec_words if w["text"].lower().startswith("korean")), None)
            veg = next((w for w in sec_words if w["text"].lower().startswith(("vegetarian", "halal"))), None)
            kor_top = kor["top"] if kor else page.height
            veg_top = veg["top"] if veg else page.height
            # bands: labels sit vertically centered in their band, so split at
            # the midpoints between consecutive label centers
            int_end = (intl_lbl["top"] + kor_top) / 2 if intl_lbl and kor else kor_top - 40
            kor_end = (kor_top + veg_top) / 2 if kor and veg else veg_top - 40
            for ci in range(len(dates)):
                date = _norm_date(dates[ci]["text"])
                col_words = [w for w in words
                             if bounds[ci] <= (w["x0"] + w["x1"]) / 2 < bounds[ci + 1]
                             and w["top"] > date_bottom + 2]
                col_words.sort(key=lambda w: (round(w["top"]), w["x0"]))
                # group into lines
                lines = []
                for w in col_words:
                    if lines and abs(w["top"] - lines[-1][0]) < 4:
                        lines[-1][1].append(w["text"])
                        lines[-1][0] = (lines[-1][0] + w["top"]) / 2
                    else:
                        lines.append([w["top"], [w["text"]]])
                def clean(band_lines):
                    items, cur, last_top = [], [], None
                    for top, toks in band_lines:
                        text = " ".join(toks).strip()
                        if not re.search(r"[A-Za-z가-힣]", text):
                            continue  # bare allergen numbers
                        if re.fullmatch(r"\(.*\)", text) or re.match(r"\(?[A-Za-z ]+:\s", text):
                            continue  # origin/allergen note lines
                        if last_top is not None and top - last_top > 14 and cur:
                            items.append(" ".join(cur)); cur = []
                        cur.append(text)
                        last_top = top
                    if cur:
                        items.append(" ".join(cur))
                    drop = re.compile(r"^(MON|TUES?|WED|THURS?|FRI)$|^GRILL|^(International|Korean|Vegetarian|Halal)$", re.I)
                    out = []
                    for i in items:
                        # Sep-style PDFs place the section label inside the
                        # column, where it merges into an item line
                        i = re.sub(r"^(International|Korean|Vegetarian/?|Halal)\s+", "", i).strip()
                        if len(i) > 1 and not drop.match(i):
                            out.append(i)
                    return out
                intl = clean([l for l in lines if l[0] < int_end])
                korean = clean([l for l in lines if int_end <= l[0] < kor_end])
                # the PDF repeats the same weeks in Korean on later pages;
                # keep the first (English) parse for each date
                if (intl or korean) and date not in days:
                    days[date] = {"international": intl, "korean": korean}
    print(f"  lunch: {len(days)} days parsed ({label})")
    return {"url": pdf_url, "label": label, "days": days, "links": links}


def main():
    # Keep previously fetched data for accounts that fail this run
    prev = {}
    out_path = os.path.join(BASE, "assets", "media.js")
    if os.path.exists(out_path):
        try:
            prev = json.loads(open(out_path).read().split("window.KIS_MEDIA = ", 1)[1].rstrip().rstrip(";"))
        except Exception:
            prev = {}
    ig = {}
    for ig_user in IG_USERS:
        print("Fetching Instagram @" + ig_user)
        try:
            ig[ig_user] = fetch_instagram(ig_user)
        except Exception as ex:
            print(f"  FAILED ({ex}); keeping previous snapshot if any")
            if prev.get("instagram", {}).get(ig_user):
                ig[ig_user] = prev["instagram"][ig_user]
        time.sleep(5)
    yt = {}
    for key, cid in YT_CHANNELS:
        print(f"Fetching YouTube {key}")
        try:
            yt[key] = fetch_youtube(cid)
        except Exception as ex:
            print(f"  FAILED ({ex}); keeping previous snapshot if any")
            if prev.get("youtube", {}).get(key):
                yt[key] = prev["youtube"][key]
    print("Fetching admissions news")
    admissions = fetch_admissions()
    # Google News RSS often returns empty for a subset of outlets per run;
    # keep the previous snapshot's articles for any outlet missing this run
    got = {a["outlet"] for a in admissions}
    carried = [a for a in prev.get("admissions", []) if a["outlet"] not in got]
    if carried:
        print(f"  carried over {len(carried)} previous articles for missing outlets")
    admissions = sorted(admissions + carried, key=lambda a: a["date"], reverse=True)
    print("Fetching upcoming events")
    try:
        events = fetch_events()
    except Exception as ex:
        print(f"  FAILED ({ex}); keeping previous snapshot if any")
        events = prev.get("events", [])
    print("Fetching KIS high school news")
    try:
        kis_news = fetch_kis_news()
    except Exception as ex:
        print(f"  FAILED ({ex}); keeping previous snapshot if any")
        kis_news = prev.get("kisNews", [])
    print("Fetching lunch menu")
    try:
        lunch = fetch_lunch()
    except Exception as ex:
        print(f"  FAILED ({ex}); keeping previous snapshot if any")
        lunch = prev.get("lunch", {})
    print("Fetching community calendar")
    try:
        community = fetch_community()
    except Exception as ex:
        print(f"  FAILED ({ex}); keeping previous snapshot if any")
        community = prev.get("community", [])
    updated = time.strftime("%Y-%m-%d %H:%M")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("// Generated by refresh_media.py — do not edit by hand\n")
        f.write("window.KIS_MEDIA = ")
        json.dump({"updated": updated, "instagram": ig, "youtube": yt,
                   "admissions": admissions, "events": events, "lunch": lunch,
                   "community": community, "kisNews": kis_news},
                  f, ensure_ascii=False, indent=2)
        f.write(";\n")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
