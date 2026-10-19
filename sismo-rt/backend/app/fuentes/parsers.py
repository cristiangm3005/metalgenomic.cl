"""Conversión de los formatos de cada proveedor a `Reporte`."""

from __future__ import annotations

from datetime import datetime, timezone

from ..modelos import Reporte

# Tipos de evento EMSC que no son sismos (voladuras de cantera, explosiones).
EMSC_NO_SISMO = ("qb", "ex")


def parse_iso(texto: str) -> datetime:
    dt = datetime.fromisoformat(texto.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_tiempo(valor) -> datetime:
    """Acepta ISO 8601 o epoch en milisegundos."""
    if isinstance(valor, (int, float)):
        return datetime.fromtimestamp(valor / 1000, tz=timezone.utc)
    return parse_iso(str(valor))


def emsc_feature(feature: dict, fuente: str = "emsc") -> Reporte | None:
    """Feature GeoJSON de EMSC (igual en el WebSocket y en el servicio FDSN con format=json).

    GlobalQuake Server 0.11 genera exactamente este formato en su FDSNWS (format=geojson).
    """
    p = feature.get("properties") or {}
    if p.get("mag") is None or p.get("lat") is None or p.get("lon") is None or not p.get("time"):
        return None
    if any(t in (p.get("evtype") or "").lower() for t in EMSC_NO_SISMO):
        return None
    unid = p.get("unid") or feature.get("id") or ""
    prof = p.get("depth")
    return Reporte(
        fuente=fuente,
        id_fuente=str(unid),
        tiempo=parse_iso(p["time"]),
        lat=float(p["lat"]),
        lon=float(p["lon"]),
        prof_km=abs(float(prof)) if prof is not None else None,
        mag=float(p["mag"]),
        tipo_mag=p.get("magtype") or "",
        lugar=(p.get("flynn_region") or "").title(),
        url=f"https://www.seismicportal.eu/eventdetails.html?unid={unid}" if unid and fuente == "emsc" else "",
    )


def emsc_ws_mensaje(mensaje: dict) -> Reporte | None:
    """Mensaje del WebSocket de EMSC: {"action": "create"|"update", "data": <Feature>}."""
    if mensaje.get("action") not in ("create", "update"):
        return None
    return emsc_feature(mensaje.get("data") or {})


def emsc_coleccion(datos: dict, fuente: str = "emsc") -> list[Reporte]:
    return [r for f in datos.get("features", []) if (r := emsc_feature(f, fuente)) is not None]


def usgs_coleccion(datos: dict) -> list[Reporte]:
    """GeoJSON de USGS (feeds de resumen o servicio FDSN con format=geojson)."""
    reportes = []
    for f in datos.get("features", []):
        p = f.get("properties") or {}
        coords = (f.get("geometry") or {}).get("coordinates") or []
        if p.get("mag") is None or p.get("time") is None or len(coords) < 2:
            continue
        if (p.get("type") or "earthquake") != "earthquake":
            continue
        reportes.append(
            Reporte(
                fuente="usgs",
                id_fuente=str(f.get("id")),
                tiempo=parse_tiempo(p["time"]),
                lat=float(coords[1]),
                lon=float(coords[0]),
                prof_km=float(coords[2]) if len(coords) > 2 and coords[2] is not None else None,
                mag=float(p["mag"]),
                tipo_mag=p.get("magType") or "",
                lugar=p.get("place") or "",
                url=p.get("url") or "",
            )
        )
    return reportes
