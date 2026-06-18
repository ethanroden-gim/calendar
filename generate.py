#!/usr/bin/env python3
"""Fetch events from the GIM calendar JSON feed (an Apps Script web app) and
render a branded static page to public/index.html.

The page shows a 5-week calendar grid (current week + next 4 weeks, Sunday-first,
with the weekend columns shrunk) followed by a full detail list. Maintenance and
holiday events are styled distinctly.

Env:
  CALENDAR_FEED_URL  full URL of the Apps Script /exec feed (incl. ?token=... if set).
                     Required unless DEMO=1.
  WEEKS              number of week rows to show (default 5).
  DEMO               if "1", render sample events instead of fetching (local preview).
"""
import os
import re
import json
import html
import urllib.request
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/New_York")
WEEKS = int(os.environ.get("WEEKS", "5"))
GRID_DAYS = WEEKS * 7
WEEKDAY_HEADERS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]  # Sunday-first
MAX_CHIPS = 3  # visible chips per grid cell before "+N more"


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
def fetch_events():
    """Return a list of normalized event dicts:
    {title, start, end, allDay, location, description, type}."""
    if os.environ.get("DEMO") == "1":
        return _sample_events()
    url = os.environ["CALENDAR_FEED_URL"]
    req = urllib.request.Request(url, headers={"User-Agent": "gim-calendar-build"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(f"Feed error: {data['error']} (check FEED_TOKEN / access).")
    return data.get("events", []) if isinstance(data, dict) else data


def parse_times(ev):
    """Return (start_dt, end_dt, all_day) in Eastern time."""
    if ev.get("allDay"):
        sd = datetime.fromisoformat(str(ev["start"])[:10]).replace(tzinfo=TZ)
        ed = datetime.fromisoformat(str(ev["end"])[:10]).replace(tzinfo=TZ)
        return sd, ed, True
    sd = datetime.fromisoformat(ev["start"]).astimezone(TZ)
    ed = datetime.fromisoformat(ev["end"]).astimezone(TZ)
    return sd, ed, False


def ev_type(ev):
    return ev.get("type") or "maintenance"


def covered_dates(sd, ed, all_day):
    """List of calendar dates an event covers (inclusive), handling Google's
    exclusive all-day end date and midnight-ending timed events."""
    first = sd.date()
    if all_day:
        last = ed.date() - timedelta(days=1)
    else:
        last = ed.date()
        if last > first and ed.hour == 0 and ed.minute == 0 and ed.second == 0:
            last -= timedelta(days=1)
    if last < first:
        last = first
    out, d = [], first
    while d <= last:
        out.append(d)
        d += timedelta(days=1)
    return out


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #
def fmt_time(dt):
    return dt.strftime("%I:%M %p").lstrip("0")


def fmt_chip_time(dt):
    """Compact time for a grid chip, e.g. '9a' or '2:30p'."""
    h = dt.strftime("%I").lstrip("0")
    m = dt.strftime("%M")
    ap = dt.strftime("%p").lower()[0]
    return f"{h}{ap}" if m == "00" else f"{h}:{m}{ap}"


def time_label(sd, ed, all_day):
    return "All day" if all_day else f"{fmt_time(sd)} – {fmt_time(ed)}"


def clean_desc(desc):
    if not desc:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", desc, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)  # strip any remaining HTML tags
    return html.unescape(text).strip()


def fmt_long(d):
    # %-d isn't portable to Windows; assemble manually.
    return d.strftime("%A, %B ") + str(d.day) + d.strftime(", %Y")


def fmt_short(d):
    return d.strftime("%b ") + str(d.day)


PIN_SVG = (
    '<svg width="13" height="13" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
    '<path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 '
    '9.5a2.5 2.5 0 110-5 2.5 2.5 0 010 5z"/></svg>'
)


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def render_grid(events, grid_start, today):
    """Render the 5-week grid. Returns HTML for the {{GRID}} placeholder."""
    grid_dates = [grid_start + timedelta(days=i) for i in range(GRID_DAYS)]
    grid_set = set(grid_dates)

    # bucket events into day cells
    buckets = {d: [] for d in grid_dates}
    for ev in events:
        sd, ed, all_day = parse_times(ev)
        for d in covered_dates(sd, ed, all_day):
            if d in grid_set:
                buckets[d].append((0 if all_day else 1, sd, all_day, ev))

    parts = ['<div class="cal-scroll"><div class="cal-grid" role="grid">']
    for name in WEEKDAY_HEADERS:
        cls = "cal-head weekend" if name in ("Sun", "Sat") else "cal-head"
        parts.append(f'<div class="{cls}">{name}</div>')

    for idx, d in enumerate(grid_dates):
        classes = ["cal-cell"]
        if d.weekday() in (5, 6):  # Sat=5, Sun=6
            classes.append("weekend")
        if d == today:
            classes.append("today")
        elif d < today:
            classes.append("past")
        parts.append(f'<div class="{" ".join(classes)}">')

        if d.day == 1 or idx == 0:
            daynum = d.strftime("%b ") + str(d.day)
        else:
            daynum = str(d.day)
        parts.append(f'<div class="cal-daynum">{daynum}</div>')

        items = sorted(buckets[d], key=lambda t: (t[0], t[1]))
        if len(items) > MAX_CHIPS:
            shown, more = items[: MAX_CHIPS - 1], len(items) - (MAX_CHIPS - 1)
        else:
            shown, more = items, 0
        for _, sd, all_day, ev in shown:
            label = html.escape(ev.get("title", ""))
            if not all_day:
                label = f'<span class="chip-t">{html.escape(fmt_chip_time(sd))}</span> ' + label
            parts.append(f'<div class="chip {ev_type(ev)}">{label}</div>')
        if more:
            parts.append(f'<div class="chip-more">+{more} more</div>')
        parts.append("</div>")

    parts.append("</div></div>")
    return "".join(parts)


def render_events(events, grid_start, grid_end):
    """Render the detail list below the grid (date-grouped agenda)."""
    in_window = []
    for ev in events:
        sd, ed, all_day = parse_times(ev)
        days = covered_dates(sd, ed, all_day)
        if any(grid_start <= d <= grid_end for d in days):
            key = max(sd.date(), grid_start)
            in_window.append((key, sd, ed, all_day, ev))

    if not in_window:
        return '<div class="empty">No scheduled events in this period.</div>'

    in_window.sort(key=lambda t: (t[0], 0 if t[3] else 1, t[1]))

    out, current = [], None
    for key, sd, ed, all_day, ev in in_window:
        if key != current:
            if current is not None:
                out.append("</section>")
            current = key
            out.append('<section class="day-group">')
            out.append(f'<div class="day-heading">{html.escape(fmt_long(key))}</div>')
        out.append(f'<div class="event {ev_type(ev)}">')
        out.append(f'<div class="event-time">{html.escape(time_label(sd, ed, all_day))}</div>')
        out.append(f'<div class="event-title">{html.escape(ev.get("title", "(no title)"))}</div>')
        loc = ev.get("location")
        if loc:
            out.append(f'<div class="event-meta">{PIN_SVG}<span>{html.escape(loc)}</span></div>')
        desc = clean_desc(ev.get("description"))
        if desc:
            out.append(f'<div class="event-desc">{html.escape(desc)}</div>')
        out.append("</div>")
    out.append("</section>")
    return "\n".join(out)


def main():
    events = fetch_events()
    now_et = datetime.now(TZ)
    today = now_et.date()
    grid_start = today - timedelta(days=(today.weekday() + 1) % 7)  # Sunday of this week
    grid_end = grid_start + timedelta(days=GRID_DAYS - 1)

    rng = f"Week of {fmt_short(grid_start)} – {fmt_short(grid_end)}, {grid_end.year}"
    updated = now_et.strftime("%b ") + str(now_et.day) + now_et.strftime(", %Y at ") + fmt_time(now_et) + " ET"

    template = open("template.html", encoding="utf-8").read()
    page = (
        template.replace("{{GRID}}", render_grid(events, grid_start, today))
        .replace("{{EVENTS}}", render_events(events, grid_start, grid_end))
        .replace("{{UPDATED}}", html.escape(updated))
        .replace("{{RANGE}}", html.escape(rng))
    )

    os.makedirs("public", exist_ok=True)
    with open("public/index.html", "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Wrote public/index.html with {len(events)} event(s).")


# --------------------------------------------------------------------------- #
# Demo data (DEMO=1) — anchored to the current grid so every cell type is exercised
# --------------------------------------------------------------------------- #
def _sample_events():
    today = datetime.now(TZ).date()
    gs = today - timedelta(days=(today.weekday() + 1) % 7)  # this week's Sunday

    def dt(day_offset, h, m=0):
        d = gs + timedelta(days=day_offset)
        return datetime(d.year, d.month, d.day, h, m, tzinfo=TZ).isoformat()

    def allday(day_offset, span=1):
        s = gs + timedelta(days=day_offset)
        e = s + timedelta(days=span)
        return s.isoformat(), e.isoformat()

    h_s, h_e = allday(1)            # holiday on Monday this week
    md_s, md_e = allday(4, span=4)  # multi-day maintenance crossing the week boundary
    return [
        {"title": "Presidents' Day", "start": h_s, "end": h_e, "allDay": True,
         "location": "", "description": "", "type": "holiday"},
        {"title": "HVAC Filter Replacement", "start": dt(2, 9), "end": dt(2, 11),
         "allDay": False, "location": "Building A, Roof Units 1-4",
         "description": "Replace all primary filters. Coordinate with facilities for roof access.",
         "type": "maintenance"},
        {"title": "Generator Load Test", "start": dt(2, 14), "end": dt(2, 15, 30),
         "allDay": False, "location": "Main Electrical Room", "description": "", "type": "maintenance"},
        {"title": "Elevator Inspection", "start": dt(2, 8), "end": dt(2, 9),
         "allDay": False, "location": "Lobby", "description": "", "type": "maintenance"},
        {"title": "Sprinkler Flush", "start": dt(2, 16), "end": dt(2, 17),
         "allDay": False, "location": "Zone 3", "description": "", "type": "maintenance"},
        {"title": "Roof Recoating", "start": md_s, "end": md_e, "allDay": True,
         "location": "Building C Roof", "description": "Weather permitting.", "type": "maintenance"},
        {"title": "Fire Suppression Inspection", "start": dt(15, 0), "end": dt(16, 0),
         "allDay": True, "location": "Entire Facility",
         "description": "Annual inspection by certified vendor.\nExpect brief alarm tests.",
         "type": "maintenance"},
        {"title": "Quarterly Safety Walk", "start": dt(23, 10), "end": dt(23, 12),
         "allDay": False, "location": "All Buildings", "description": "", "type": "maintenance"},
    ]


if __name__ == "__main__":
    main()
