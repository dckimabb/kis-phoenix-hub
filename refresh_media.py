#!/usr/bin/env python3
"""Snapshot KIS school data into assets/media.js.

Instagram and YouTube stay as committed snapshots until their API integrations
are available. Other school feeds are refreshed daily by GitHub Actions.

Usage: python3 refresh_media.py
"""
import json, os, re, subprocess, time

BASE = os.path.dirname(os.path.abspath(__file__))
INSTA_DIR = os.path.join(BASE, "assets", "insta")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126 Safari/537.36")

EVENTS_PAGE = "https://www.kis.or.kr/academics/high-school"
EVENTS_ELEMENT = "19287"  # fsEl_19287 = HS Upcoming Events calendar slideshow


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


def _unescape(s):
    import html as _html
    return _html.unescape(re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s, flags=re.S)).strip()




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


def _timestamp():
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())


def _refresh_source(key, fetcher, fallback, source_updated, source_errors):
    try:
        value = fetcher()
    except Exception as ex:
        source_errors[key] = str(ex)
        print(f"  FAILED ({ex}); keeping previous snapshot if any")
        return fallback
    source_updated[key] = _timestamp()
    source_errors.pop(key, None)
    return value


def main():
    # Keep the last successful value and timestamp for any source that fails.
    out_path = os.path.join(BASE, "assets", "media.js")
    prev = {}
    if os.path.exists(out_path):
        try:
            previous_text = open(out_path, encoding="utf-8").read()
            prev = json.loads(previous_text.split("window.KIS_MEDIA = ", 1)[1].rstrip().rstrip(";"))
        except Exception:
            prev = {}

    source_updated = dict(prev.get("sourceUpdated", {}))
    source_errors = {}
    # Keep social snapshots as offline fallbacks. Instagram will be updated
    # manually until KIS approves an API integration; YouTube is fetched live
    # by the Vercel endpoint in api/youtube.js.
    ig = prev.get("instagram", {})
    yt = prev.get("youtube", {})

    print("Fetching upcoming events from KIS")
    events = _refresh_source("events", fetch_events, prev.get("events", []),
                             source_updated, source_errors)
    print("Fetching KIS high school news")
    kis_news = _refresh_source("kisNews", fetch_kis_news, prev.get("kisNews", []),
                               source_updated, source_errors)
    print("Fetching lunch menu from KIS")
    lunch = _refresh_source("lunch", fetch_lunch, prev.get("lunch", {}),
                            source_updated, source_errors)
    print("Fetching KIS community calendar")
    community = _refresh_source("community", fetch_community,
                                prev.get("community", []), source_updated, source_errors)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("// Generated by refresh_media.py — do not edit by hand\n")
        f.write("window.KIS_MEDIA = ")
        json.dump({"updated": _timestamp(), "sourceUpdated": source_updated,
                   "sourceErrors": source_errors, "instagram": ig, "youtube": yt,
                   "events": events, "lunch": lunch, "community": community,
                   "kisNews": kis_news},
                  f, ensure_ascii=False, indent=2)
        f.write(";\n")
    print(f"Wrote {out_path}")

    failed_kis_sources = [key for key in ("events", "kisNews", "lunch", "community")
                          if key in source_errors]
    if failed_kis_sources:
        raise SystemExit("KIS source refresh failed: " + ", ".join(failed_kis_sources))


if __name__ == "__main__":
    main()
