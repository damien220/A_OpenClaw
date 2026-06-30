"""Weather heartbeat source — current conditions via Open-Meteo (no API key needed)."""

import json
from urllib.request import Request, urlopen
from urllib.error import URLError
from urllib.parse import quote_plus

from heartbeat.sources.base import BaseSource

from logger_pkg import get_logger

logger = get_logger(__name__)

_WMO_CODES: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Icy fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    77: "Snow grains",
    80: "Slight showers", 81: "Moderate showers", 82: "Violent showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}

_WIND_DIRS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def _fetch_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent": "A_OpenClaw/0.1"})
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _wind_direction(degrees: float) -> str:
    return _WIND_DIRS[round(degrees / 22.5) % 16]


class WeatherSource(BaseSource):
    """Fetch current weather conditions for a configured location.

    Config keys:
        location (str): City name, e.g. "Paris". Required.
        units (str): "metric" (°C, km/h) or "imperial" (°F, mph). Default: metric.
    """

    def gather(self) -> str:
        location = self.config.get("location", "").strip()
        if not location:
            logger.warning("WeatherSource: no location configured", extra={"source": self.name})
            return ""

        units = self.config.get("units", "metric").lower()
        if units not in ("metric", "imperial"):
            units = "metric"

        temp_unit = "celsius" if units == "metric" else "fahrenheit"
        wind_unit = "kmh" if units == "metric" else "mph"
        temp_sym = "°C" if units == "metric" else "°F"
        wind_label = "km/h" if units == "metric" else "mph"

        # Geocode
        try:
            geo = _fetch_json(
                "https://geocoding-api.open-meteo.com/v1/search"
                f"?name={quote_plus(location)}&count=1&language=en&format=json"
            )
        except (URLError, TimeoutError, json.JSONDecodeError) as e:
            logger.error("WeatherSource geocoding failed", extra={"location": location, "error": str(e)})
            return f"[weather source: geocoding error — {e}]"

        places = geo.get("results")
        if not places:
            return f"[weather source: location not found: {location!r}]"

        place = places[0]
        lat, lon = place["latitude"], place["longitude"]
        display = ", ".join(filter(None, [
            place.get("name", location),
            place.get("admin1", ""),
            place.get("country", ""),
        ]))

        # Fetch weather
        try:
            data = _fetch_json(
                "https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat}&longitude={lon}"
                "&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
                "weather_code,wind_speed_10m,wind_direction_10m"
                f"&temperature_unit={temp_unit}"
                f"&wind_speed_unit={wind_unit}"
                "&timezone=auto"
            )
        except (URLError, TimeoutError, json.JSONDecodeError) as e:
            logger.error("WeatherSource fetch failed", extra={"location": display, "error": str(e)})
            return f"[weather source: API error — {e}]"

        cur = data.get("current", {})
        code = cur.get("weather_code", 0)
        description = _WMO_CODES.get(code, f"Unknown (WMO {code})")
        temp = cur.get("temperature_2m", "?")
        feels = cur.get("apparent_temperature", "?")
        humidity = cur.get("relative_humidity_2m", "?")
        wind_speed = cur.get("wind_speed_10m", "?")
        wind_deg = cur.get("wind_direction_10m")
        wind_dir = _wind_direction(wind_deg) if wind_deg is not None else "?"

        logger.info("WeatherSource gathered", extra={"location": display, "code": code})

        return (
            f"### Source: {self.name} (Weather)\n\n"
            f"**{display}** — {description}\n"
            f"- Temp: {temp}{temp_sym} (feels like {feels}{temp_sym})\n"
            f"- Humidity: {humidity}%\n"
            f"- Wind: {wind_speed} {wind_label} {wind_dir}\n"
        )
