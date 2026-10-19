"""Configuración leída de variables de entorno (y de un archivo .env opcional)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

RAIZ_BACKEND = Path(__file__).resolve().parent.parent


def cargar_env(ruta: Path) -> None:
    """Carga un .env simple (CLAVE=valor) sin pisar variables ya definidas."""
    if not ruta.is_file():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


def _lista(texto: str) -> tuple[str, ...]:
    return tuple(p.strip().lower() for p in texto.split(",") if p.strip())


def _bool(texto: str) -> bool:
    return texto.strip().lower() in {"1", "true", "si", "sí", "yes", "on"}


@dataclass(frozen=True)
class Config:
    # Fuentes: emsc_ws (push en tiempo real), usgs (polling de respaldo/confirmación),
    # emsc_rest (polling que solo se activa si el WebSocket de EMSC cae).
    fuentes: tuple[str, ...] = ("emsc_ws", "usgs", "emsc_rest")
    emsc_ws_url: str = "wss://www.seismicportal.eu/standing_order/websocket"
    usgs_url: str = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson"
    usgs_intervalo_s: float = 30.0
    emsc_rest_url: str = "https://www.seismicportal.eu/fdsnws/event/1/query"
    emsc_rest_intervalo_s: float = 30.0
    emsc_fallback_tras_s: float = 20.0
    # FDSNWS-event de GlobalQuake Server 0.11 (p. ej. http://localhost:8080). Vacío = no se usa.
    globalquake_url: str = ""
    globalquake_intervalo_s: float = 5.0

    # Filtro por defecto: notificar si está a <= radio_km O si la magnitud es >= mag_global.
    radio_km: float = 500.0
    mag_global: float = 6.0
    # Nivel "alerta" (y no "info") si mag >= mag_alerta Y la intensidad estimada en sitio >= mmi_alerta.
    mag_alerta: float = 4.0
    mmi_alerta: float = 3.0
    # No notificar eventos que llegan con más antigüedad que esto (solo se muestran en el mapa).
    max_edad_alerta_min: float = 30.0
    mag_min_mapa: float = 2.5

    # Velocidades medias de onda (km/s) para estimar llegadas P y S.
    vp_km_s: float = 6.5
    vs_km_s: float = 3.75

    max_eventos: int = 1000
    retencion_h: float = 24.0

    # Ingesta externa (p. ej. fork de GlobalQuake). Vacío = deshabilitada.
    ingest_token: str = ""
    simulacion: bool = False
    cors_origenes: tuple[str, ...] = ("*",)

    # Push al celular vía ntfy para una ubicación fija (casa/oficina). Opcional.
    ntfy_topic: str = ""
    ntfy_server: str = "https://ntfy.sh"
    ntfy_token: str = ""
    casa_lat: float | None = None
    casa_lon: float | None = None
    casa_nombre: str = "Casa"

    @classmethod
    def desde_entorno(cls, archivo_env: Path | None = RAIZ_BACKEND / ".env") -> "Config":
        if archivo_env is not None:
            cargar_env(archivo_env)
        e = os.environ.get
        d = cls()

        def f(nombre: str, defecto: float) -> float:
            return float(e(nombre, str(defecto)))

        casa_lat, casa_lon = e("CASA_LAT", ""), e("CASA_LON", "")
        return cls(
            fuentes=_lista(e("FUENTES", ",".join(d.fuentes))),
            emsc_ws_url=e("EMSC_WS_URL", d.emsc_ws_url),
            usgs_url=e("USGS_URL", d.usgs_url),
            usgs_intervalo_s=f("USGS_INTERVALO_S", d.usgs_intervalo_s),
            emsc_rest_url=e("EMSC_REST_URL", d.emsc_rest_url),
            emsc_rest_intervalo_s=f("EMSC_REST_INTERVALO_S", d.emsc_rest_intervalo_s),
            emsc_fallback_tras_s=f("EMSC_FALLBACK_TRAS_S", d.emsc_fallback_tras_s),
            globalquake_url=e("GLOBALQUAKE_URL", "").rstrip("/"),
            globalquake_intervalo_s=f("GLOBALQUAKE_INTERVALO_S", d.globalquake_intervalo_s),
            radio_km=f("RADIO_KM", d.radio_km),
            mag_global=f("MAG_GLOBAL", d.mag_global),
            mag_alerta=f("MAG_ALERTA", d.mag_alerta),
            mmi_alerta=f("MMI_ALERTA", d.mmi_alerta),
            max_edad_alerta_min=f("MAX_EDAD_ALERTA_MIN", d.max_edad_alerta_min),
            mag_min_mapa=f("MAG_MIN_MAPA", d.mag_min_mapa),
            vp_km_s=f("VP_KM_S", d.vp_km_s),
            vs_km_s=f("VS_KM_S", d.vs_km_s),
            max_eventos=int(e("MAX_EVENTOS", str(d.max_eventos))),
            retencion_h=f("RETENCION_H", d.retencion_h),
            ingest_token=e("INGEST_TOKEN", ""),
            simulacion=_bool(e("SIMULACION", "false")),
            cors_origenes=tuple(o.strip() for o in e("CORS_ORIGENES", "*").split(",") if o.strip()),
            ntfy_topic=e("NTFY_TOPIC", ""),
            ntfy_server=e("NTFY_SERVER", d.ntfy_server).rstrip("/"),
            ntfy_token=e("NTFY_TOKEN", ""),
            casa_lat=float(casa_lat) if casa_lat else None,
            casa_lon=float(casa_lon) if casa_lon else None,
            casa_nombre=e("CASA_NOMBRE", d.casa_nombre),
        )
