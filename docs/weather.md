# Weather

Weather is an opt-in framework feature. Configure it in **Options → System
Settings → Extra Features → Weather**, or in the same step of first-run setup.

1. Enable weather and enter an OpenWeather API key with access to
   [Current Weather](https://openweathermap.org/api/current) and
   [Geocoding](https://openweathermap.org/api/geocoding-api). Each deployment
   supplies its own provider account and appropriate subscription.
2. Search by city, optionally adding a country code (for example `Tripoli,LY`).
   The location builder works like the Sidebar builder: select a search result
   and **Add** it, then select a chosen location to **Set as default**, move it
   up or down, rename it in the inspector panel, or **Remove** it. Up to ten
   locations.
3. Choose Celsius or Fahrenheit, a display style, and a placement, then save.

Display styles are **icon only**, **temperature only**, **icon + temperature**,
and **full** (icon, temperature and condition text); 1.10.0b1's *condition text*
is read as full. Placements are **titlebar**, **user hub**, **floating**, and
**project embeds only**.

**Floating** is a round bubble, like an assistant's launcher: the icon, with the
temperature as a badge (the condition text is in its panel). It starts in the
chosen corner (start/end follow the UI's LTR/RTL direction); each user can drag
it anywhere, it snaps to the nearer side, and the position is kept as that
user's preference (`weather_float_position`), so it follows them across devices.
Its panel opens away from the edges it sits against. The corner selector stays
disabled, with a tooltip, unless Floating is selected.

**Preview**: Extra Features lifts the Options modal off the live page like the
visual steps, so placement, display, units and corner can be tried before
saving. In a preview the widget's reading request carries the draft token, so it
reads the unsaved settings too.

Titlebar and User hub placements make weather a **titlebar action**, like
Search or Notifications: it appears in **System Settings → Titlebar → action
order** (after Notifications by default) and can be reordered there, it takes
the bar's button shape, and it groups into the action rail on narrow screens.
Titlebar keeps it in the bar under every hub style. User hub follows the hub: it
sits in the user-hub dropdown card, or in the bar when the hub style lays its
actions out there. Only an icon fits the round button, so the temperature and
text displays widen it into a pill. A centred title is centred on the bar
itself, not between its sides, so the pill neither moves the title nor makes it
jump when the reading loads.

Click an indicator to open its panel, placed the way the notifications panel
is (under the trigger, under the rail when grouped, across the width under the
header on phones). It shows the location selector (a Dlux choice selector),
condition, temperature,
feels-like temperature, observation time, and provider attribution. Escape or
an outside click closes it. The dashboard card keeps these details visible.
The location selector changes only that widget; it does not change the system
default or other users' settings. English and Arabic interface text is included;
weather descriptions use the active interface language supported by OpenWeather.

Turning weather off disables its settings with explanatory tooltips, preserves
the key and locations, and renders no weather widgets. Authenticated users may
read weather for configured locations only. Location searches require a
superuser and an enabled settings draft, so a new key/location can be tested
before saving. A disabled deployment's weather read endpoint returns 404.

## Add weather to a project dashboard

In a template extending `dlux/base.html`, such as a CRM dashboard:

```django
{% load dlux_weather %}
{% weather_widget variant="card" %}
```

For a compact clickable indicator:

```django
{% load dlux_weather %}
{% weather_widget %}
```

Both use System Settings automatically. No project view, credentials, JavaScript
initialization, or API requests are needed. Assets are included once per request.
The tag renders nothing for anonymous users or while weather is disabled.
Choose **Project embeds only** to keep the dashboard card without shell weather.

An optional `location="32.88720,13.19130"` chooses a configured location by its
normalized five-decimal `lat,lon` ID; unknown IDs render nothing. Omit it to use
the system default. The `placement` argument is reserved for the framework's
shell slots; project embeds should omit it.

Floating offsets can be adjusted in project CSS to accommodate other controls:

```css
:root {
  --dlux-weather-bottom-offset: 4.5rem;
  --dlux-weather-top-offset: 5rem;
  --dlux-weather-side-offset: .5rem;
}
```

## Storage, caching, and operation

Configuration lives in `SystemSettings.extra_config['weather']`; project-owned
`extra_config['app']` namespaces remain intact. No migration is needed. Defaults
and normalization live in `dlux/system/weather.py`. Read runtime configuration
through `dlux.weather.get_weather_config()` (server-side only).

The key is encrypted with a key derived from Django's `SECRET_KEY`, never filled
back into the form, and excluded from portable settings export/import. Leave its
field blank to retain it. Enter it again after rotating `SECRET_KEY` or importing
settings into a new deployment. Imports retain an existing destination key.

**The calls to OpenWeather run in the Celery worker, so the worker needs a route
out.** In a Dlux-generated stack neither web nor celery can reach the internet:
only `smtp-relay` and the Composer agent sit on the `egress` network. Weather
therefore needs one deliberate change to `compose.yml`, giving the `celery`
service the network the scaffold already declares:

```yaml
  celery:
    networks:
      - internal
      - egress
```

This is an interim exception to the network rule in [Outbound Requests](outbound-requests.md); the relay replaces it. Recreate the service afterwards (`./start.sh`). Keep `web` off `egress`: that is
the point of the split. Granting the worker egress lets every Celery task reach
the internet, so do it only if you accept that. Without it the settings page says
the worker has no route to the internet (city search answers `502 network`), and
readings stay on *Loading*. A stack whose Celery worker is not running makes the
calls from web instead, which works where web can reach the internet, such as a
development server.

Web queues a task and the worker calls OpenWeather (HTTPS, four-second timeout,
bounded responses, no redirects) and writes the answer to the shared cache, which
web reads:

- **Readings.** Web serves the cached reading. When it is missing or older than
  15 minutes, web queues `dlux.tasks.weather_refresh`, at most once per reading
  every 30 seconds. Until a first reading exists the endpoint answers `202
  {"status": "pending"}` and the widget shows *Loading* and asks again every
  three seconds (six times). A failed fetch is reported (`503`) rather than left
  pending. A reading older than 15 minutes is served while it refreshes, marked
  stale, for up to 24 hours; an observation older than two hours is also stale.
- **City search** (superusers only). Web queues `dlux.tasks.weather_search` and
  waits up to ten seconds for its answer. An unsaved key is encrypted before it
  reaches the broker. Errors say which fix applies: a refused key
  (`credentials`), or a provider the server cannot reach (`provider`, or `worker`
  when no worker answered).

Tasks are sent by name, so the worker must run DjangoLux 1.10.0b2 or later (a
deployment's web and celery always do). Web checks for a live worker once a
minute. **Without one** (a project with no Celery, or `CELERY_BROKER_URL`
unset) web makes the calls itself, which works where web can reach the
internet, such as a development server.

The worker and web share Django's default cache, so it must be a shared backend
(Redis, as generated stacks use); LocMemCache is per process and would never see
the worker's answer. Widgets on the same page share in-flight requests, and
hidden browser tabs skip the periodic 15-minute refresh.

Endpoints: `GET /sys/api/weather/?location=<configured-id>` and administrator
`POST /sys/api/weather/locations/` (CSRF protected, body: `query`, `enabled: true`,
optional draft `api_key`). Neither response includes credentials. New assets
require `collectstatic` when installing into a deployed project.

If an administrator's search reports a key error, check the account/key status
and access to both APIs. For local Python installations without a usable CA
bundle, configure a trusted bundle through `SSL_CERT_FILE`; do not disable TLS
verification. On this development Mac, `/etc/ssl/cert.pem` supplies that bundle.
