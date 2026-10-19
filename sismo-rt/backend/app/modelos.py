"""Modelos internos: reportes de cada fuente, eventos fusionados y filtros de usuario."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import sismologia as sis
from .config import Config

# Cuanto mayor, más confiable: el valor "oficial" del evento sale de la fuente de mayor prioridad.
PRIORIDAD_FUENTE = {"usgs": 3, "emsc": 2, "globalquake": 1, "simulacion": 0}
CATALOGOS = {"usgs", "emsc"}


def ahora() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def epoch_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


@dataclass
class Reporte:
    """Lo que dice UNA fuente sobre un sismo."""

    fuente: str
    id_fuente: str
    tiempo: datetime  # hora de origen, UTC
    lat: float
    lon: float
    prof_km: float | None
    mag: float
    tipo_mag: str = ""
    lugar: str = ""
    url: str = ""
    recibido: datetime = field(default_factory=ahora)

    @property
    def prioridad(self) -> int:
        return PRIORIDAD_FUENTE.get(self.fuente, 0)


@dataclass
class Evento:
    """Un sismo real, fusionando los reportes de todas las fuentes que lo informaron."""

    id: str
    reportes: dict[str, Reporte]
    creado: datetime = field(default_factory=ahora)
    version: int = 1

    @property
    def principal(self) -> Reporte:
        return max(self.reportes.values(), key=lambda r: (r.prioridad, r.recibido))

    @property
    def confirmado(self) -> bool:
        return any(f in CATALOGOS for f in self.reportes)

    def a_dict(self) -> dict:
        p = self.principal
        return {
            "id": self.id,
            "version": self.version,
            "tiempo": iso(p.tiempo),
            "tiempo_ms": epoch_ms(p.tiempo),
            "lat": round(p.lat, 4),
            "lon": round(p.lon, 4),
            "prof_km": None if p.prof_km is None else round(p.prof_km, 1),
            "mag": round(p.mag, 1),
            "tipo_mag": p.tipo_mag,
            "lugar": p.lugar,
            "url": p.url,
            "fuente_principal": p.fuente,
            "fuentes": sorted(self.reportes),
            "confirmado": self.confirmado,
            "detectado": iso(self.creado),
            # Retraso entre la hora de origen y el momento en que el servidor supo del sismo.
            "latencia_s": round((self.creado - min(r.tiempo for r in self.reportes.values())).total_seconds(), 1),
        }


@dataclass
class Filtro:
    """Ubicación y preferencias de un cliente."""

    lat: float
    lon: float
    radio_km: float
    mag_global: float
    mag_min: float = 0.0  # magnitud mínima para recibir el evento (mapa)

    @classmethod
    def por_defecto(cls, cfg: Config, lat: float, lon: float, **extra) -> "Filtro":
        valores = {"radio_km": cfg.radio_km, "mag_global": cfg.mag_global, "mag_min": cfg.mag_min_mapa}
        valores.update({k: v for k, v in extra.items() if v is not None})
        return cls(lat=lat, lon=lon, **valores)


def evaluar(evento: Evento, filtro: Filtro, cfg: Config, momento: datetime | None = None) -> dict:
    """Calcula lo que el sismo significa PARA ESTE usuario: distancia, intensidad, llegada de ondas, nivel."""
    momento = momento or ahora()
    p = evento.principal
    dist = sis.distancia_km(filtro.lat, filtro.lon, p.lat, p.lon)
    r_hipo = sis.distancia_hipocentral_km(dist, p.prof_km)
    mmi = sis.mmi_allen2012(p.mag, r_hipo)
    llegada_p, llegada_s = sis.tiempos_llegada(p.tiempo, r_hipo, cfg.vp_km_s, cfg.vs_km_s)

    cerca = dist <= filtro.radio_km
    grande = p.mag >= filtro.mag_global
    reciente = (momento - p.tiempo).total_seconds() <= cfg.max_edad_alerta_min * 60
    relevante = cerca or grande
    if not relevante:
        nivel = None
    elif p.mag >= cfg.mag_alerta and mmi >= cfg.mmi_alerta:
        nivel = "alerta"
    else:
        nivel = "info"

    return {
        "distancia_km": round(dist, 1),
        "distancia_hipocentral_km": round(r_hipo, 1),
        "rumbo": sis.rumbo(filtro.lat, filtro.lon, p.lat, p.lon),
        "mmi": round(mmi, 1),
        "mmi_romano": sis.romano(mmi),
        "mmi_descripcion": sis.DESCRIPCION_MMI[sis.mmi_entero(mmi)],
        "pga_g": round(sis.pga_desde_mmi(mmi), 4),
        "llegada_p_ms": epoch_ms(llegada_p),
        "llegada_s_ms": epoch_ms(llegada_s),
        "s_restante_s": round((llegada_s - momento).total_seconds(), 1),
        "relevante": relevante,
        "motivo": ("cerca" if cerca else "magnitud") if relevante else None,
        "nivel": nivel,
        "reciente": reciente,
    }
