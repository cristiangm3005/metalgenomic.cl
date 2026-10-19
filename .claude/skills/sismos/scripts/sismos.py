#!/usr/bin/env python3
"""Vigilante de sismos para la skill `sismos` de Claude Code.

Subcomandos:
  ahora    Lista los sismos recientes cerca de tu ubicación (consulta única).
  vigilar  Proceso continuo: imprime UNA línea por cada sismo relevante nuevo.
           Pensado para el tool Monitor: cada línea despierta a Claude.
  prueba   Imprime un sismo ficticio con el mismo formato (para probar el aviso).

Fuentes:
  - Si defines SISMOS_RT_URL (backend sismo-rt de este repo), escucha su flujo SSE en
    tiempo real, que incluye el WebSocket de EMSC y las detecciones de GlobalQuake
    enviadas a /api/ingest. Si ese flujo se cae, pasa automáticamente al polling.
  - Si defines SISMOS_GQ_URL (p. ej. http://localhost:8080), consulta cada pocos segundos el
    servidor FDSNWS-event que trae GlobalQuake Server 0.11 (detecciones propias, en segundos).
  - Además consulta cada 30 s los catálogos públicos de USGS y EMSC.

Solo usa la biblioteca estándar de Python (3.9+).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

USER_AGENT = "claude-skill-sismos/1.0"
USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
EMSC_URL = "https://www.seismicportal.eu/fdsnws/event/1/query"
ESTADO_DEF = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "claude-skill-sismos" / "estado.json"

DESCRIPCION_MMI = {1: "No sentido", 2: "Muy débil", 3: "Débil", 4: "Ligero", 5: "Moderado",
                   6: "Fuerte", 7: "Muy fuerte", 8: "Severo", 9: "Violento", 10: "Extremo"}
ROMANOS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]


# --------------------------------------------------------------------------- cálculos

def distancia_km(lat1, lon1, lat2, lon2) -> float:
    """Haversine."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0088 * math.asin(min(1.0, math.sqrt(a)))


def rumbo(lat1, lon1, lat2, lon2) -> str:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    g = (math.degrees(math.atan2(x, y)) + 360) % 360
    return ["N", "NE", "E", "SE", "S", "SO", "O", "NO"][int((g + 22.5) // 45) % 8]


def mmi_estimada(mag: float, dist_km: float, prof_km: float | None) -> float:
    """Intensidad de Mercalli en tu ubicación: Allen, Wald & Worden (2012), versión con distancia
    hipocentral (coeficientes de openquake.hazardlib.gsim.allen_2012_ipe.AllenEtAl2012Rhypo)."""
    r_hipo = math.hypot(dist_km, max(prof_km or 0.0, 0.0))
    r_m = -0.209 + 2.042 * math.exp(mag - 5)
    mmi = 2.085 + 1.428 * mag - 1.402 * math.log(math.sqrt(r_hipo**2 + r_m**2))
    if r_hipo > 50:  # término anelástico
        mmi += 0.078 * math.log(r_hipo / 50)
    return min(10.0, max(1.0, mmi))


# --------------------------------------------------------------------------- modelo

@dataclass
class Config:
    lat: float
    lon: float
    lugar: str
    radio_km: float
    mag_global: float
    mag_min: float
    intervalo_s: float
    rt_url: str
    estado: Path
    gq_url: str = ""
    gq_intervalo_s: float = 5.0


@dataclass
class Sismo:
    fuente: str
    id: str
    tiempo: datetime
    lat: float
    lon: float
    prof_km: float | None
    mag: float
    lugar: str = ""
    url: str = ""
    fuentes: set = field(default_factory=set)
    confirmado: bool = True

    def evaluar(self, cfg: Config) -> dict:
        d = distancia_km(cfg.lat, cfg.lon, self.lat, self.lon)
        mmi = mmi_estimada(self.mag, d, self.prof_km)
        cerca, grande = d <= cfg.radio_km, self.mag >= cfg.mag_global
        if not (cerca or grande) or self.mag < cfg.mag_min:
            nivel = None
        elif self.mag >= 4.0 and mmi >= 3.0:
            nivel = "ALERTA"
        else:
            nivel = "INFO"
        return {"dist": d, "mmi": mmi, "rumbo": rumbo(cfg.lat, cfg.lon, self.lat, self.lon), "nivel": nivel}


def _iso(texto: str) -> datetime:
    dt = datetime.fromisoformat(str(texto).strip().replace("Z", "+00:00"))
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def parse_usgs(datos: dict) -> list[Sismo]:
    res = []
    for f in datos.get("features", []):
        p, c = f.get("properties") or {}, (f.get("geometry") or {}).get("coordinates") or []
        if p.get("mag") is None or len(c) < 2 or (p.get("type") or "earthquake") != "earthquake":
            continue
        res.append(Sismo("usgs", str(f.get("id")), datetime.fromtimestamp(p["time"] / 1000, tz=timezone.utc),
                         float(c[1]), float(c[0]), float(c[2]) if len(c) > 2 and c[2] is not None else None,
                         float(p["mag"]), p.get("place") or "", p.get("url") or "", {"usgs"}))
    return res


def parse_emsc(datos: dict, fuente: str = "emsc") -> list[Sismo]:
    """GeoJSON estilo EMSC. GlobalQuake Server usa el mismo formato en su FDSNWS (format=geojson)."""
    res = []
    for f in datos.get("features", []):
        p = f.get("properties") or {}
        if p.get("mag") is None or p.get("lat") is None or p.get("lon") is None or not p.get("time"):
            continue
        if any(t in (p.get("evtype") or "").lower() for t in ("qb", "ex")):
            continue
        unid = str(p.get("unid") or f.get("id") or "")
        prof = p.get("depth")
        url = f"https://www.seismicportal.eu/eventdetails.html?unid={unid}" if fuente == "emsc" else ""
        res.append(Sismo(fuente, unid, _iso(p["time"]), float(p["lat"]), float(p["lon"]),
                         abs(float(prof)) if prof is not None else None, float(p["mag"]),
                         (p.get("flynn_region") or "").title(), url, {fuente},
                         confirmado=fuente != "globalquake"))
    return res


def parse_sismo_rt(msg: dict) -> Sismo:
    e = msg["evento"]
    return Sismo(e.get("fuente_principal", "sismo-rt"), e["id"], _iso(e["tiempo"]), e["lat"], e["lon"],
                 e.get("prof_km"), e["mag"], e.get("lugar") or "", e.get("url") or "",
                 set(e.get("fuentes") or []), bool(e.get("confirmado", True)))


# --------------------------------------------------------------------------- red

def get_json(url: str, params: dict, timeout: float = 20) -> dict:
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}",
                                 headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        cuerpo = r.read() if r.status != 204 else b""
    return json.loads(cuerpo) if cuerpo.strip() else {"features": []}


def consultar_gq(cfg: Config, desde: datetime) -> list[Sismo]:
    """Servidor FDSNWS-event de GlobalQuake Server (Settings: autoStartFDSNWSEventServer=true, puerto 8080).

    Ese servidor no implementa búsqueda por radio, así que se piden todos y se filtra aquí.
    Responde 204 (sin contenido) cuando no hay sismos.
    """
    datos = get_json(f"{cfg.gq_url.rstrip('/')}/fdsnws/event/1/query",
                     {"format": "geojson", "starttime": desde.strftime("%Y-%m-%dT%H:%M:%S"),
                      "minmag": cfg.mag_min}, timeout=10)
    return parse_emsc(datos, fuente="globalquake")


def consultar(cfg: Config, desde: datetime) -> tuple[list[Sismo], list[str]]:
    """Consulta USGS y EMSC: sismos cercanos (M ≥ mag_min) + sismos grandes en todo el mundo
    (M ≥ mag_global). Devuelve (sismos fusionados, errores por fuente)."""
    t = desde.strftime("%Y-%m-%dT%H:%M:%S")
    sismos, errores = [], []
    peticiones = [
        ("usgs", parse_usgs, USGS_URL, {"format": "geojson", "starttime": t, "latitude": cfg.lat,
                                        "longitude": cfg.lon, "maxradiuskm": cfg.radio_km,
                                        "minmagnitude": cfg.mag_min, "orderby": "time"}),
        ("usgs", parse_usgs, USGS_URL, {"format": "geojson", "starttime": t,
                                        "minmagnitude": max(cfg.mag_global, cfg.mag_min), "orderby": "time"}),
        ("emsc", parse_emsc, EMSC_URL, {"format": "json", "starttime": t, "lat": cfg.lat, "lon": cfg.lon,
                                        "maxradius": round(cfg.radio_km / 111.195, 3), "minmag": cfg.mag_min,
                                        "orderby": "time", "limit": 500}),
        ("emsc", parse_emsc, EMSC_URL, {"format": "json", "starttime": t,
                                        "minmag": max(cfg.mag_global, cfg.mag_min), "orderby": "time",
                                        "limit": 500}),
    ]
    vistos = set()
    for nombre, parser, url, params in peticiones:
        try:
            for s in parser(get_json(url, params)):
                if (s.fuente, s.id) not in vistos:  # un sismo grande y cercano sale en ambas consultas
                    vistos.add((s.fuente, s.id))
                    sismos.append(s)
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, OSError) as exc:
            errores.append(f"{nombre}: {exc}")
    if cfg.gq_url:
        try:
            sismos.extend(consultar_gq(cfg, desde))
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, OSError) as exc:
            errores.append(f"globalquake: {exc}")
    return fusionar(sismos), errores


def fusionar(sismos: list[Sismo]) -> list[Sismo]:
    """Un mismo sismo de varias fuentes (≤90 s y ≤150 km) se une; manda USGS, luego EMSC, luego GlobalQuake."""
    orden = {"usgs": 0, "emsc": 1}
    res: list[Sismo] = []
    for s in sorted(sismos, key=lambda x: (orden.get(x.fuente, 2), x.tiempo)):
        igual = next((r for r in res if abs((r.tiempo - s.tiempo).total_seconds()) <= 90
                      and distancia_km(r.lat, r.lon, s.lat, s.lon) <= 150), None)
        if igual:
            igual.fuentes |= s.fuentes
            igual.confirmado = igual.confirmado or s.confirmado
        else:
            res.append(s)
    return sorted(res, key=lambda x: x.tiempo, reverse=True)


# --------------------------------------------------------------------------- salida

def hora_chile(dt: datetime) -> str:
    try:
        from zoneinfo import ZoneInfo
        return dt.astimezone(ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def linea(s: Sismo, ev: dict, cfg: Config, actualizacion: bool = False) -> str:
    hace = (datetime.now(timezone.utc) - s.tiempo).total_seconds() / 60
    m = int(min(10, max(1, round(ev["mmi"]))))
    prof = f"{s.prof_km:.0f} km" if s.prof_km is not None else "?"
    partes = [
        f"SISMO nivel={ev['nivel']}{' (actualización)' if actualizacion else ''}",
        f"M{s.mag:.1f} a {ev['dist']:.0f} km al {ev['rumbo']} de {cfg.lugar}",
        f"intensidad estimada {ROMANOS[m - 1]} ({DESCRIPCION_MMI[m]})",
        f"prof {prof}",
        f"{hora_chile(s.tiempo)} (hace {hace:.0f} min)",
        s.lugar or f"{s.lat:.2f},{s.lon:.2f}",
        f"fuentes={','.join(sorted(s.fuentes)) or s.fuente}{'' if s.confirmado else ' SIN_CONFIRMAR'}",
    ]
    if s.url:
        partes.append(s.url)
    return " | ".join(partes)


def emitir(texto: str) -> None:
    print(texto, flush=True)


# --------------------------------------------------------------------------- estado

class Memoria:
    """Recuerda qué sismos ya se avisaron (también entre reinicios del monitor)."""

    def __init__(self, ruta: Path):
        self.ruta = ruta
        self.items: list[dict] = []
        try:
            self.items = json.loads(ruta.read_text())["avisados"]
        except (OSError, ValueError, KeyError):
            pass
        self.lock = threading.Lock()

    def buscar(self, s: Sismo) -> dict | None:
        for a in self.items:
            if s.id in a["ids"] or (abs((_iso(a["t"]) - s.tiempo).total_seconds()) <= 90
                                     and distancia_km(a["lat"], a["lon"], s.lat, s.lon) <= 150):
                return a
        return None

    def decidir(self, s: Sismo, nivel: str) -> str | None:
        """Devuelve 'nuevo', 'actualizacion' o None (no avisar)."""
        rango = {"INFO": 1, "ALERTA": 2}
        with self.lock:
            a = self.buscar(s)
            if a is None:
                self.items.append({"ids": [s.id], "t": s.tiempo.isoformat(), "lat": s.lat, "lon": s.lon,
                                   "mag": s.mag, "nivel": nivel})
                self._guardar()
                return "nuevo"
            if s.id not in a["ids"]:
                a["ids"].append(s.id)
            sube = rango[nivel] > rango.get(a["nivel"], 0) or s.mag >= a["mag"] + 0.5
            if sube:
                a["mag"], a["nivel"] = max(a["mag"], s.mag), max(nivel, a["nivel"], key=rango.get)
            self._guardar()
            return "actualizacion" if sube else None

    def _guardar(self) -> None:
        limite = datetime.now(timezone.utc) - timedelta(days=2)
        self.items = [a for a in self.items if _iso(a["t"]) >= limite]
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps({"avisados": self.items}))
        tmp.replace(self.ruta)


class Estados:
    """Emite una línea ESTADO solo cuando una fuente cambia entre ok y caída (para que el silencio no engañe)."""

    def __init__(self):
        self.actual: dict[str, bool] = {}

    def marcar(self, fuente: str, ok: bool, detalle: str = "") -> None:
        if self.actual.get(fuente) == ok:
            return
        primera = fuente not in self.actual
        self.actual[fuente] = ok
        if ok and primera:
            return  # arranque normal: no hace falta avisar
        emitir(f"ESTADO fuente={fuente} {'RECUPERADA' if ok else 'CAIDA'}{(' | ' + detalle[:200]) if detalle else ''}")


# --------------------------------------------------------------------------- modos

def procesar(s: Sismo, cfg: Config, memoria: Memoria, max_edad_min: float) -> str | None:
    if (datetime.now(timezone.utc) - s.tiempo).total_seconds() > max_edad_min * 60:
        return None
    ev = s.evaluar(cfg)
    if ev["nivel"] is None:
        return None
    accion = memoria.decidir(s, ev["nivel"])
    return linea(s, ev, cfg, accion == "actualizacion") if accion else None


def escuchar_sse(cfg: Config, memoria: Memoria, estados: Estados, conectado: threading.Event,
                 max_edad_min: float) -> None:
    params = urllib.parse.urlencode({"lat": cfg.lat, "lon": cfg.lon, "radio_km": cfg.radio_km,
                                     "mag_global": cfg.mag_global, "mag_min": cfg.mag_min})
    url = f"{cfg.rt_url.rstrip('/')}/api/stream?{params}"
    espera = 2.0
    while True:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/event-stream"})
            with urllib.request.urlopen(req, timeout=60) as r:
                conectado.set()
                estados.marcar("sismo-rt", True)
                espera, evento, datos = 2.0, "", []
                for crudo in r:
                    l = crudo.decode("utf-8").rstrip("\r\n")
                    if l.startswith("event:"):
                        evento = l[6:].strip()
                    elif l.startswith("data:"):
                        datos.append(l[5:].strip())
                    elif l == "" and datos:
                        if evento == "sismo":
                            msg = json.loads("\n".join(datos))
                            if msg.get("notificar"):
                                texto = procesar(parse_sismo_rt(msg), cfg, memoria, max_edad_min)
                                if texto:
                                    emitir(texto)
                        evento, datos = "", []
        except Exception as exc:  # red, servidor caído, JSON inválido...
            conectado.clear()
            estados.marcar("sismo-rt", False, str(exc))
        time.sleep(espera)
        espera = min(espera * 2, 60)


def vigilar(cfg: Config, max_edad_min: float) -> None:
    memoria, estados = Memoria(cfg.estado), Estados()
    sse_ok = threading.Event()
    if cfg.rt_url:
        threading.Thread(target=escuchar_sse, args=(cfg, memoria, estados, sse_ok, max_edad_min),
                         daemon=True).start()
        time.sleep(3)
    ultimo_catalogo = 0.0
    while True:
        desde = datetime.now(timezone.utc) - timedelta(minutes=max_edad_min)
        sismos = []
        # GlobalQuake local se consulta cada pocos segundos: es la fuente rápida.
        if cfg.gq_url:
            try:
                sismos.extend(consultar_gq(cfg, desde))
                estados.marcar("globalquake", True)
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError, OSError) as exc:
                estados.marcar("globalquake", False, str(exc))
        # Con el flujo en tiempo real de sismo-rt activo no hace falta consultar los catálogos.
        if not sse_ok.is_set() and time.monotonic() - ultimo_catalogo >= cfg.intervalo_s:
            ultimo_catalogo = time.monotonic()
            sin_gq = Config(**{**cfg.__dict__, "gq_url": ""})
            catalogo, errores = consultar(sin_gq, desde)
            sismos.extend(catalogo)
            caidas = {e.split(":", 1)[0] for e in errores}
            for f in ("usgs", "emsc"):
                estados.marcar(f, f not in caidas, next((e for e in errores if e.startswith(f)), ""))
        for s in sorted(fusionar(sismos), key=lambda x: x.tiempo):
            texto = procesar(s, cfg, memoria, max_edad_min)
            if texto:
                emitir(texto)
        time.sleep(min(cfg.gq_intervalo_s, cfg.intervalo_s) if cfg.gq_url else cfg.intervalo_s)


def ahora(cfg: Config, horas: float, como_json: bool) -> int:
    sismos, errores = consultar(cfg, datetime.now(timezone.utc) - timedelta(hours=horas))
    filas = []
    for s in sismos:
        ev = s.evaluar(cfg)
        if ev["nivel"] or ev["dist"] <= cfg.radio_km:
            filas.append((s, ev))
    if como_json:
        print(json.dumps([{"tiempo": s.tiempo.isoformat(), "hora_chile": hora_chile(s.tiempo), "mag": s.mag,
                           "lat": s.lat, "lon": s.lon, "prof_km": s.prof_km, "lugar": s.lugar,
                           "distancia_km": round(ev["dist"], 1), "rumbo": ev["rumbo"],
                           "mmi": round(ev["mmi"], 1), "nivel": ev["nivel"], "fuentes": sorted(s.fuentes),
                           "url": s.url} for s, ev in filas], ensure_ascii=False, indent=1))
    else:
        print(f"Sismos de las últimas {horas:g} h a ≤{cfg.radio_km:g} km de {cfg.lugar} "
              f"o M≥{cfg.mag_global:g} en el mundo (M≥{cfg.mag_min:g}): {len(filas)}")
        for s, ev in filas:
            print("  " + linea(s, ev, cfg).replace(f"SISMO nivel={ev['nivel']} | ", f"[{ev['nivel'] or '-'}] "))
    for e in errores:
        print(f"ERROR fuente {e}", file=sys.stderr)
    return 2 if {"usgs", "emsc"} <= {e.split(":", 1)[0] for e in errores} else 0


def prueba(cfg: Config) -> None:
    s = Sismo("prueba", "prueba", datetime.now(timezone.utc) - timedelta(seconds=40),
              cfg.lat - 0.3, cfg.lon - 0.4, 30.0, 5.6, "SISMO DE PRUEBA (ficticio)", "", {"prueba"})
    emitir(linea(s, s.evaluar(cfg), cfg))


# --------------------------------------------------------------------------- CLI

def main(argv=None) -> int:
    e = os.environ.get
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("modo", choices=["ahora", "vigilar", "prueba"])
    ap.add_argument("--lat", type=float, default=float(e("SISMOS_LAT", "-27.3668")))
    ap.add_argument("--lon", type=float, default=float(e("SISMOS_LON", "-70.3314")))
    ap.add_argument("--lugar", default=e("SISMOS_LUGAR", "Copiapó"))
    ap.add_argument("--radio-km", type=float, default=float(e("SISMOS_RADIO_KM", "500")),
                    help="avisar sismos a esta distancia o menos (def. 500)")
    ap.add_argument("--mag-global", type=float, default=float(e("SISMOS_MAG_GLOBAL", "6.0")),
                    help="avisar sismos de esta magnitud o más en cualquier lugar (def. 6.0)")
    ap.add_argument("--mag-min", type=float, default=float(e("SISMOS_MAG_MIN", "3.0")),
                    help="ignorar sismos menores a esta magnitud (def. 3.0)")
    ap.add_argument("--intervalo", type=float, default=float(e("SISMOS_INTERVALO_S", "30")))
    ap.add_argument("--horas", type=float, default=24, help="modo ahora: horas hacia atrás (def. 24)")
    ap.add_argument("--max-edad-min", type=float, default=30,
                    help="modo vigilar: no avisar sismos más antiguos que esto (def. 30)")
    ap.add_argument("--json", action="store_true", help="modo ahora: salida JSON")
    ap.add_argument("--rt-url", default=e("SISMOS_RT_URL", ""),
                    help="URL del backend sismo-rt (tiempo real + GlobalQuake). Opcional.")
    ap.add_argument("--gq-url", default=e("SISMOS_GQ_URL", ""),
                    help="URL del FDSNWS de GlobalQuake Server, p. ej. http://localhost:8080. Opcional.")
    ap.add_argument("--estado", type=Path, default=Path(e("SISMOS_ESTADO", str(ESTADO_DEF))))
    a = ap.parse_args(argv)
    cfg = Config(a.lat, a.lon, a.lugar, a.radio_km, a.mag_global, a.mag_min, a.intervalo, a.rt_url, a.estado,
                 gq_url=a.gq_url)

    if a.modo == "ahora":
        return ahora(cfg, a.horas, a.json)
    if a.modo == "prueba":
        prueba(cfg)
        return 0
    emitir(f"VIGILANDO {cfg.lugar} ({cfg.lat}, {cfg.lon}) | radio {cfg.radio_km:g} km o M≥{cfg.mag_global:g} "
           f"| M≥{cfg.mag_min:g} | fuentes: "
           + " + ".join(x for x in (
               f"GlobalQuake {cfg.gq_url} cada {cfg.gq_intervalo_s:g}s" if cfg.gq_url else "",
               f"sismo-rt {cfg.rt_url}" if cfg.rt_url else "",
               f"USGS+EMSC cada {cfg.intervalo_s:g}s" + (" (si cae sismo-rt)" if cfg.rt_url else ""),
           ) if x))
    vigilar(cfg, a.max_edad_min)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
