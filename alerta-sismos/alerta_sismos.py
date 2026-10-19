#!/usr/bin/env python3
"""Alerta de sismos cerca de tu ubicación (por defecto: Copiapó, Chile).

Consulta cada minuto los catálogos públicos de USGS y EMSC, calcula la
distancia a tus coordenadas y, si un sismo cumple alguna de tus reglas
(radio + magnitud mínima), te avisa por Telegram y/o ntfy.sh (push al celular).

Solo usa la biblioteca estándar de Python (3.9+).

IMPORTANTE: esto NO reemplaza al sistema oficial de alertas (SAE de SENAPRED)
ni a la información del Centro Sismológico Nacional (sismologia.cl). Los
catálogos publican los sismos con algunos minutos de retraso.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

USER_AGENT = "alerta-sismos/1.0 (+https://github.com/cristiangm3005/metalgenomic.cl)"
HERE = Path(__file__).resolve().parent
TZ_CHILE_NOMBRE = "America/Santiago"


# --------------------------------------------------------------------------
# Configuración
# --------------------------------------------------------------------------

def cargar_env(ruta: Path) -> None:
    """Carga un archivo .env simple (CLAVE=valor) sin pisar variables ya definidas."""
    if not ruta.is_file():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        valor = valor.strip().strip('"').strip("'")
        os.environ.setdefault(clave.strip(), valor)


@dataclass
class Regla:
    radio_km: float
    mag_min: float


def parsear_reglas(texto: str) -> list[Regla]:
    """'100:3.5,300:4.5,1000:6.5' -> [Regla(100, 3.5), ...]"""
    reglas = []
    for parte in texto.split(","):
        parte = parte.strip()
        if not parte:
            continue
        radio, mag = parte.split(":")
        reglas.append(Regla(float(radio), float(mag)))
    if not reglas:
        raise ValueError("Debes definir al menos una regla RADIO_KM:MAGNITUD")
    return sorted(reglas, key=lambda r: r.radio_km)


@dataclass
class Config:
    lat: float
    lon: float
    lugar: str
    reglas: list[Regla]
    intervalo_s: int
    ventana_min: int
    estado: Path
    fuentes: list[str]
    telegram_token: str = ""
    telegram_chat_id: str = ""
    ntfy_topic: str = ""
    ntfy_server: str = "https://ntfy.sh"
    ntfy_token: str = ""

    @property
    def radio_max_km(self) -> float:
        return max(r.radio_km for r in self.reglas)

    @property
    def mag_min_global(self) -> float:
        return min(r.mag_min for r in self.reglas)

    @classmethod
    def desde_entorno(cls) -> "Config":
        e = os.environ.get
        return cls(
            lat=float(e("LAT", "-27.3668")),
            lon=float(e("LON", "-70.3314")),
            lugar=e("LUGAR", "Copiapó"),
            reglas=parsear_reglas(e("REGLAS", "100:3.5,300:4.5,800:6.0,2000:7.0")),
            intervalo_s=int(e("INTERVALO_S", "60")),
            ventana_min=int(e("VENTANA_MIN", "60")),
            estado=Path(e("ARCHIVO_ESTADO", str(HERE / "estado.json"))),
            fuentes=[f.strip().lower() for f in e("FUENTES", "usgs,emsc").split(",") if f.strip()],
            telegram_token=e("TELEGRAM_TOKEN", ""),
            telegram_chat_id=e("TELEGRAM_CHAT_ID", ""),
            ntfy_topic=e("NTFY_TOPIC", ""),
            ntfy_server=e("NTFY_SERVER", "https://ntfy.sh").rstrip("/"),
            ntfy_token=e("NTFY_TOKEN", ""),
        )


# --------------------------------------------------------------------------
# Modelo y utilidades
# --------------------------------------------------------------------------

@dataclass
class Sismo:
    fuente: str
    id: str
    tiempo: datetime  # UTC
    lat: float
    lon: float
    prof_km: float | None
    mag: float
    tipo_mag: str
    lugar: str
    url: str
    distancia_km: float = field(default=0.0)


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia de gran círculo (haversine) en km."""
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def rumbo(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """Dirección aproximada (N, NE, ...) desde el punto 1 hacia el punto 2."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    grados = (math.degrees(math.atan2(x, y)) + 360) % 360
    puntos = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
    return puntos[int((grados + 22.5) // 45) % 8]


def regla_que_cumple(sismo: Sismo, reglas: list[Regla]) -> Regla | None:
    for regla in reglas:  # ordenadas de menor a mayor radio
        if sismo.distancia_km <= regla.radio_km and sismo.mag >= regla.mag_min:
            return regla
    return None


def hora_local(dt: datetime) -> str:
    try:
        from zoneinfo import ZoneInfo

        return dt.astimezone(ZoneInfo(TZ_CHILE_NOMBRE)).strftime("%d-%m-%Y %H:%M:%S")
    except Exception:  # sin base de zonas horarias instalada
        return dt.strftime("%d-%m-%Y %H:%M:%S UTC")


def _parse_iso(texto: str) -> datetime:
    texto = texto.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(texto)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def http_get_json(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status == 204:  # FDSN: sin resultados
            return {"features": []}
        cuerpo = resp.read()
    if not cuerpo.strip():
        return {"features": []}
    return json.loads(cuerpo)


# --------------------------------------------------------------------------
# Fuentes de datos
# --------------------------------------------------------------------------

def url_usgs(cfg: Config, desde: datetime) -> str:
    params = {
        "format": "geojson",
        "starttime": desde.strftime("%Y-%m-%dT%H:%M:%S"),
        "latitude": cfg.lat,
        "longitude": cfg.lon,
        "maxradiuskm": int(min(cfg.radio_max_km, 20000)),
        "minmagnitude": cfg.mag_min_global,
        "orderby": "time",
    }
    return "https://earthquake.usgs.gov/fdsnws/event/1/query?" + urllib.parse.urlencode(params)


def parse_usgs(datos: dict) -> list[Sismo]:
    sismos = []
    for f in datos.get("features", []):
        p = f.get("properties") or {}
        coords = (f.get("geometry") or {}).get("coordinates") or []
        if p.get("mag") is None or len(coords) < 2:
            continue
        sismos.append(
            Sismo(
                fuente="USGS",
                id=f"usgs:{f.get('id')}",
                tiempo=datetime.fromtimestamp(p["time"] / 1000, tz=timezone.utc),
                lat=float(coords[1]),
                lon=float(coords[0]),
                prof_km=float(coords[2]) if len(coords) > 2 and coords[2] is not None else None,
                mag=float(p["mag"]),
                tipo_mag=p.get("magType") or "",
                lugar=p.get("place") or "",
                url=p.get("url") or "",
            )
        )
    return sismos


def url_emsc(cfg: Config, desde: datetime) -> str:
    params = {
        "format": "json",
        "starttime": desde.strftime("%Y-%m-%dT%H:%M:%S"),
        "lat": cfg.lat,
        "lon": cfg.lon,
        "maxradius": round(min(cfg.radio_max_km, 20000) / 111.195, 3),  # grados
        "minmag": cfg.mag_min_global,
        "orderby": "time",
        "limit": 200,
    }
    return "https://www.seismicportal.eu/fdsnws/event/1/query?" + urllib.parse.urlencode(params)


def parse_emsc(datos: dict) -> list[Sismo]:
    sismos = []
    for f in datos.get("features", []):
        p = f.get("properties") or {}
        if p.get("mag") is None or p.get("lat") is None or p.get("lon") is None:
            continue
        unid = p.get("unid") or f.get("id") or ""
        prof = p.get("depth")
        sismos.append(
            Sismo(
                fuente="EMSC",
                id=f"emsc:{unid}",
                tiempo=_parse_iso(p["time"]),
                lat=float(p["lat"]),
                lon=float(p["lon"]),
                prof_km=abs(float(prof)) if prof is not None else None,
                mag=float(p["mag"]),
                tipo_mag=p.get("magtype") or "",
                lugar=(p.get("flynn_region") or "").title(),
                url=f"https://www.seismicportal.eu/eventdetails.html?unid={unid}" if unid else "",
            )
        )
    return sismos


FUENTES = {
    "usgs": (url_usgs, parse_usgs),
    "emsc": (url_emsc, parse_emsc),
}


def obtener_sismos(cfg: Config) -> list[Sismo]:
    desde = datetime.now(timezone.utc) - timedelta(minutes=cfg.ventana_min)
    resultado = []
    for nombre in cfg.fuentes:
        if nombre not in FUENTES:
            log(f"Fuente desconocida '{nombre}', se ignora (opciones: {', '.join(FUENTES)})")
            continue
        hacer_url, parsear = FUENTES[nombre]
        try:
            resultado.extend(parsear(http_get_json(hacer_url(cfg, desde))))
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
            log(f"[{nombre}] error consultando la fuente: {exc}")
    for s in resultado:
        s.distancia_km = distancia_km(cfg.lat, cfg.lon, s.lat, s.lon)
    return resultado


# --------------------------------------------------------------------------
# Estado (para no repetir alertas)
# --------------------------------------------------------------------------

class Estado:
    """Recuerda los sismos ya avisados para no duplicar alertas.

    Un mismo sismo aparece en USGS y EMSC con IDs distintos, así que además del
    ID se considera duplicado si ocurre a <= 90 s y <= 100 km de otro ya avisado.
    """

    RETENCION = timedelta(days=2)

    def __init__(self, ruta: Path):
        self.ruta = ruta
        self.avisados: list[dict] = []
        if ruta.is_file():
            try:
                self.avisados = json.loads(ruta.read_text(encoding="utf-8")).get("avisados", [])
            except (ValueError, OSError):
                self.avisados = []

    def buscar(self, s: Sismo) -> dict | None:
        for a in self.avisados:
            if s.id in a["ids"]:
                return a
            dt = abs((_parse_iso(a["tiempo"]) - s.tiempo).total_seconds())
            if dt <= 90 and distancia_km(a["lat"], a["lon"], s.lat, s.lon) <= 100:
                return a
        return None

    def registrar(self, s: Sismo, previo: dict | None) -> None:
        if previo is None:
            self.avisados.append(
                {"ids": [s.id], "tiempo": s.tiempo.isoformat(), "lat": s.lat, "lon": s.lon, "mag": s.mag}
            )
        else:
            if s.id not in previo["ids"]:
                previo["ids"].append(s.id)
            previo["mag"] = max(previo["mag"], s.mag)

    def guardar(self) -> None:
        limite = datetime.now(timezone.utc) - self.RETENCION
        self.avisados = [a for a in self.avisados if _parse_iso(a["tiempo"]) >= limite]
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps({"avisados": self.avisados}, indent=1), encoding="utf-8")
        tmp.replace(self.ruta)


# --------------------------------------------------------------------------
# Notificaciones
# --------------------------------------------------------------------------

def formatear(s: Sismo, cfg: Config, actualizacion: bool = False) -> tuple[str, str]:
    titulo = f"{'Actualización: ' if actualizacion else ''}Sismo M{s.mag:.1f} a {s.distancia_km:.0f} km de {cfg.lugar}"
    prof = f"{s.prof_km:.0f} km" if s.prof_km is not None else "s/i"
    lineas = [
        f"Magnitud: {s.mag:.1f} {s.tipo_mag}".rstrip(),
        f"Hora (Chile): {hora_local(s.tiempo)}",
        f"Ubicación: {s.lugar or f'{s.lat:.2f}, {s.lon:.2f}'}",
        f"Distancia: {s.distancia_km:.0f} km al {rumbo(cfg.lat, cfg.lon, s.lat, s.lon)} de {cfg.lugar}",
        f"Profundidad: {prof}",
        f"Fuente: {s.fuente}",
    ]
    if s.url:
        lineas.append(s.url)
    lineas.append("Info oficial: sismologia.cl / SENAPRED")
    return titulo, "\n".join(lineas)


def prioridad_ntfy(s: Sismo) -> str:
    if s.mag >= 6.5 or (s.mag >= 5.5 and s.distancia_km <= 200):
        return "urgent"
    if s.mag >= 5.0:
        return "high"
    return "default"


def enviar_telegram(cfg: Config, titulo: str, cuerpo: str) -> None:
    if not (cfg.telegram_token and cfg.telegram_chat_id):
        return
    url = f"https://api.telegram.org/bot{cfg.telegram_token}/sendMessage"
    datos = urllib.parse.urlencode(
        {"chat_id": cfg.telegram_chat_id, "text": f"🌎 {titulo}\n\n{cuerpo}", "disable_web_page_preview": "true"}
    ).encode()
    req = urllib.request.Request(url, data=datos, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        resp.read()


def enviar_ntfy(cfg: Config, titulo: str, cuerpo: str, prioridad: str = "default") -> None:
    if not cfg.ntfy_topic:
        return
    headers = {
        "User-Agent": USER_AGENT,
        # Las cabeceras HTTP deben ir en latin-1; ntfy acepta RFC 2047 para UTF-8.
        "Title": "=?UTF-8?B?" + base64.b64encode(titulo.encode()).decode() + "?=",
        "Priority": prioridad,
        "Tags": "warning,earth_americas",
    }
    if cfg.ntfy_token:
        headers["Authorization"] = f"Bearer {cfg.ntfy_token}"
    req = urllib.request.Request(f"{cfg.ntfy_server}/{cfg.ntfy_topic}", data=cuerpo.encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        resp.read()


def notificar(cfg: Config, titulo: str, cuerpo: str, prioridad: str = "default") -> None:
    log(f"ALERTA: {titulo}\n{cuerpo}")
    for nombre, envio in (("Telegram", lambda: enviar_telegram(cfg, titulo, cuerpo)),
                          ("ntfy", lambda: enviar_ntfy(cfg, titulo, cuerpo, prioridad))):
        try:
            envio()
        except (urllib.error.URLError, TimeoutError) as exc:
            log(f"[{nombre}] no se pudo enviar la notificación: {exc}")


# --------------------------------------------------------------------------
# Ciclo principal
# --------------------------------------------------------------------------

def log(msg: str) -> None:
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ahora}] {msg}", flush=True)


def procesar(cfg: Config, sismos: list[Sismo], estado: Estado) -> int:
    """Evalúa los sismos contra las reglas y notifica. Devuelve cuántas alertas envió."""
    enviados = 0
    for s in sorted(sismos, key=lambda x: x.tiempo):
        if regla_que_cumple(s, cfg.reglas) is None:
            continue
        previo = estado.buscar(s)
        if previo is None:
            titulo, cuerpo = formatear(s, cfg)
        elif s.mag >= previo["mag"] + 0.5:  # magnitud revisada fuertemente al alza
            titulo, cuerpo = formatear(s, cfg, actualizacion=True)
        else:
            estado.registrar(s, previo)
            continue
        notificar(cfg, titulo, cuerpo, prioridad_ntfy(s))
        estado.registrar(s, previo)
        enviados += 1
    estado.guardar()
    return enviados


def ciclo(cfg: Config, estado: Estado) -> None:
    sismos = obtener_sismos(cfg)
    n = procesar(cfg, sismos, estado)
    log(f"{len(sismos)} sismos revisados en la ventana de {cfg.ventana_min} min, {n} alerta(s) enviada(s).")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Alertas de sismos cerca de tu ubicación (USGS + EMSC).")
    ap.add_argument("--env", default=str(HERE / ".env"), help="archivo .env con la configuración")
    ap.add_argument("--once", action="store_true", help="consulta una vez y termina (útil con cron)")
    ap.add_argument("--prueba", action="store_true", help="envía una notificación de prueba y termina")
    ap.add_argument("--listar", action="store_true",
                    help="muestra los sismos de la ventana con su distancia, sin notificar")
    args = ap.parse_args(argv)

    cargar_env(Path(args.env))
    cfg = Config.desde_entorno()
    reglas_txt = ", ".join(f"M{r.mag_min:g}+ a ≤{r.radio_km:g} km" for r in cfg.reglas)
    canales = [c for c, ok in (("Telegram", cfg.telegram_token and cfg.telegram_chat_id),
                               ("ntfy", cfg.ntfy_topic)) if ok] or ["solo consola"]
    log(f"Vigilando {cfg.lugar} ({cfg.lat}, {cfg.lon}) | reglas: {reglas_txt} | "
        f"fuentes: {', '.join(cfg.fuentes)} | avisos: {', '.join(canales)}")

    if args.prueba:
        notificar(cfg, f"Prueba de alerta-sismos ({cfg.lugar})",
                  "Si ves este mensaje, las notificaciones funcionan. ✅")
        return 0

    if args.listar:
        for s in sorted(obtener_sismos(cfg), key=lambda x: x.tiempo):
            marca = "ALERTA" if regla_que_cumple(s, cfg.reglas) else "      "
            print(f"{marca} {hora_local(s.tiempo)}  M{s.mag:<4.1f} {s.distancia_km:6.0f} km  "
                  f"[{s.fuente}] {s.lugar}")
        return 0

    estado = Estado(cfg.estado)
    if args.once:
        ciclo(cfg, estado)
        return 0

    while True:
        try:
            ciclo(cfg, estado)
        except Exception as exc:  # el vigilante nunca debe morir por un error puntual
            log(f"Error inesperado: {exc!r}")
        time.sleep(cfg.intervalo_s)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
