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

Display styles are **icon**, **condition text**, **temperature**, and
**icon + temperature**. Placements are **titlebar**, **user hub**, **floating**,
and **project embeds only**. The floating chip offers four corners: start/end
follow the UI's LTR/RTL direction. The corner selector stays disabled, with a
tooltip, unless Floating is selected.

Titlebar and User hub placements make weather a **titlebar action**, like
Search or Notifications: it appears in **System Settings → Titlebar → action
order** (after Notifications by default) and can be reordered there, it takes
the bar's button shape, and it groups into the action rail on narrow screens.
Titlebar keeps it in the bar under every hub style. User hub follows the hub: it
sits in the user-hub dropdown card, or in the bar when the hub style lays its
actions out there. Only an icon fits the round button, so the temperature and
text displays widen it into a pill.

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

The Django endpoint calls OpenWeather over HTTPS with a four-second timeout,
bounded responses, and no redirects. Browser requests stay same-origin. Cached
readings are fresh for 15 minutes; refresh failures may serve the last reading
for up to 24 hours, explicitly marked stale. Observations older than two hours
are also marked stale. Without a cached reading the widget says unavailable.
Refresh contention/failures back off for 30 seconds. No scheduled worker is
required: visible pages refresh on demand and every 15 minutes.

Caching uses Django's default cache. Configure a shared backend (for example
Redis) to share readings, refresh locks, and search throttles across web workers;
LocMemCache shares only within each process. Widgets on the same page share
in-flight requests. Hidden browser tabs skip periodic refreshes.

Endpoints: `GET /sys/api/weather/?location=<configured-id>` and administrator
`POST /sys/api/weather/locations/` (CSRF protected, body: `query`, `enabled: true`,
optional draft `api_key`). Neither response includes credentials. New assets
require `collectstatic` when installing into a deployed project.

If an administrator's search reports a key error, check the account/key status
and access to both APIs. For local Python installations without a usable CA
bundle, configure a trusted bundle through `SSL_CERT_FILE`; do not disable TLS
verification. On this development Mac, `/etc/ssl/cert.pem` supplies that bundle.
