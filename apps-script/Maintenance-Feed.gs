/**
 * GIM MAINTENANCE CALENDAR — public JSON feed
 * -------------------------------------------
 * A tiny, standalone Apps Script that exposes ONLY the maintenance calendar as
 * JSON, so the GitHub Pages site can render it. It runs under your Google
 * account's authorization (same model as the Meeting Dashboard) — no service
 * account, no key files.
 *
 * SETUP
 *   1. script.google.com → New project → paste this file.
 *   2. Editor → Services (+) → add "Calendar API" (advanced service).
 *   3. Deploy → New deployment → type "Web app":
 *        - Execute as: Me
 *        - Who has access: Anyone
 *      Copy the /exec URL.
 *   4. (Optional, recommended) lock it down: Project Settings → Script
 *      Properties → add FEED_TOKEN = <some random string>. Then the feed only
 *      responds to <exec-url>?token=<that string>. Use that full URL as the
 *      CALENDAR_FEED_URL secret in GitHub.
 */

// Calendars to read. Each event is tagged with the calendar's `type` so the
// page can style maintenance vs. holidays differently.
const CALENDARS = [
  {
    id: 'c_011ab1d11b9179320e205449f4476366f311a597cdd8b3599e0c0dc6be0b4663@group.calendar.google.com',
    type: 'maintenance'
  },
  {
    id: 'en.usa#holiday@group.v.calendar.google.com',
    type: 'holiday'
  }
];

// Window buffer (days). We reach back a week so the grid's Sunday-of-this-week
// start is always covered, and forward six weeks to cover the 5-week grid.
const WINDOW_PAST_DAYS = 7;
const WINDOW_FUTURE_DAYS = 42;

function doGet(e) {
  const required = PropertiesService.getScriptProperties().getProperty('FEED_TOKEN');
  const provided = (e && e.parameter && e.parameter.token) || '';
  if (required && provided !== required) {
    return json_({ error: 'forbidden' });
  }

  const now = new Date();
  const start = new Date(now.getTime() - WINDOW_PAST_DAYS * 86400000);
  const end = new Date(now.getTime() + WINDOW_FUTURE_DAYS * 86400000);

  const events = [];
  const warnings = [];

  CALENDARS.forEach(function (cal) {
    // Isolate each calendar so a failure on one (e.g. holidays) can't break the feed.
    try {
      let pageToken = null;
      do {
        const resp = Calendar.Events.list(cal.id, {
          timeMin: start.toISOString(),
          timeMax: end.toISOString(),
          singleEvents: true,
          orderBy: 'startTime',
          maxResults: 250,
          showDeleted: false,
          pageToken: pageToken
        });
        (resp.items || []).forEach(function (ev) {
          if (ev.status === 'cancelled') return;
          const allDay = !!(ev.start && ev.start.date);
          events.push({
            title: ev.summary || '(no title)',
            start: allDay ? ev.start.date : (ev.start && ev.start.dateTime),
            end: allDay ? (ev.end && ev.end.date) : (ev.end && ev.end.dateTime),
            allDay: allDay,
            location: ev.location || '',
            description: ev.description || '',
            type: cal.type
          });
        });
        pageToken = resp.nextPageToken;
      } while (pageToken);
    } catch (err) {
      warnings.push('Could not read ' + cal.type + ' calendar: ' + err.message);
    }
  });

  return json_({ updated: new Date().toISOString(), events: events, warnings: warnings });
}

function json_(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
