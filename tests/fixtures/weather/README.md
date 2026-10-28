# MET Norway forecast fixture

`met-locationforecast.json` is the unchanged HTTPS response retrieved on 2026-10-27 from the Locationforecast compact endpoint at the official public example coordinate, latitude 60 and longitude 11.

Source: https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=60&lon=11

Data from MET Norway. Licensed under CC BY 4.0: https://creativecommons.org/licenses/by/4.0/.

The fixture is a model forecast, not a local weather observation. Outer HTTP tests can alter conditions or return transport failures; the shipped client, cache, HQ endpoint, and browser remain intact.
