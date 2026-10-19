"""Fuentes de datos sísmicos.

- `EmscWebSocket`: canal principal, push en tiempo real (sin polling).
- `UsgsPoller`: respaldo y confirmación independiente vía la API REST/GeoJSON de USGS.
- `EmscRestFallback`: polling a EMSC que se activa solo si el WebSocket está caído.
- `GlobalQuakeFdsnws`: polling rápido al servidor FDSNWS-event de GlobalQuake Server 0.11.

Otros detectores propios pueden enviar reportes por `POST /api/ingest`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime, timedelta, timezone

import httpx

from ..bus import Bus
from ..config import Config
from . import parsers

log = logging.getLogger("sismo.fuentes")
USER_AGENT = "sismo-rt/1.0 (+https://github.com/cristiangm3005/metalgenomic.cl)"


class Fuente:
    nombre = "fuente"

    def __init__(self, cfg: Config, bus: Bus):
        self.cfg = cfg
        self.bus = bus
        self.ultimo_ok: datetime | None = None

    def estado(self, estado: str, **extra) -> None:
        self.bus.actualizar_fuente(self.nombre, estado=estado, **extra)

    def publicar(self, reportes) -> int:
        n = 0
        for r in reportes:
            if r is not None and self.bus.recibir(r) is not None:
                n += 1
        info = self.bus.estado_fuentes.setdefault(self.nombre, {"eventos": 0, "errores": 0})
        info["eventos"] = info.get("eventos", 0) + len([r for r in reportes if r is not None])
        return n

    def error(self, exc: BaseException) -> None:
        info = self.bus.estado_fuentes.setdefault(self.nombre, {"eventos": 0, "errores": 0})
        info["errores"] = info.get("errores", 0) + 1
        info["ultimo_error"] = f"{type(exc).__name__}: {exc}"[:300]
        log.warning("[%s] %s", self.nombre, info["ultimo_error"])

    async def correr(self) -> None:  # pragma: no cover - lo implementan las subclases
        raise NotImplementedError


class EmscWebSocket(Fuente):
    """WebSocket "standing order" de EMSC: empuja cada sismo nuevo o actualizado del mundo."""

    nombre = "emsc_ws"

    async def correr(self) -> None:
        import websockets

        espera = 1.0
        while True:
            self.estado("conectando")
            try:
                async with websockets.connect(
                    self.cfg.emsc_ws_url,
                    ping_interval=15,
                    ping_timeout=20,
                    open_timeout=15,
                    user_agent_header=USER_AGENT,
                ) as ws:
                    self.estado("conectado")
                    espera = 1.0
                    async for crudo in ws:
                        self.ultimo_ok = datetime.now(timezone.utc)
                        try:
                            self.publicar([parsers.emsc_ws_mensaje(json.loads(crudo))])
                        except (ValueError, KeyError, TypeError) as exc:
                            self.error(exc)
                        self.bus.estado_fuentes[self.nombre]["ultimo_mensaje"] = self.ultimo_ok.isoformat(
                            timespec="seconds")
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # red, TLS, cierre remoto...
                self.error(exc)
            self.estado("desconectado")
            # Reconexión con backoff exponencial + jitter (máx. 60 s).
            await asyncio.sleep(espera + random.uniform(0, espera / 2))
            espera = min(espera * 2, 60.0)


class Poller(Fuente):
    """Base para fuentes REST consultadas periódicamente."""

    intervalo_s = 30.0

    def __init__(self, cfg: Config, bus: Bus, cliente: httpx.AsyncClient | None = None):
        super().__init__(cfg, bus)
        self.cliente = cliente

    async def consultar(self, cliente: httpx.AsyncClient) -> list:  # pragma: no cover
        raise NotImplementedError

    def activo(self) -> bool:
        return True

    async def correr(self) -> None:
        cliente = self.cliente or httpx.AsyncClient(
            timeout=15, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
        try:
            while True:
                if not self.activo():
                    self.estado("en_espera")
                    await asyncio.sleep(2)
                    continue
                try:
                    nuevos = self.publicar(await self.consultar(cliente))
                    self.ultimo_ok = datetime.now(timezone.utc)
                    self.estado("ok", ultimo_mensaje=self.ultimo_ok.isoformat(timespec="seconds"))
                    if nuevos:
                        log.info("[%s] %d evento(s) nuevo(s) o actualizado(s)", self.nombre, nuevos)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.error(exc)
                    self.estado("error")
                await asyncio.sleep(self.intervalo_s)
        finally:
            if self.cliente is None:
                await cliente.aclose()


class UsgsPoller(Poller):
    nombre = "usgs"

    def __init__(self, cfg: Config, bus: Bus, cliente: httpx.AsyncClient | None = None):
        super().__init__(cfg, bus, cliente)
        self.intervalo_s = cfg.usgs_intervalo_s

    async def consultar(self, cliente: httpx.AsyncClient) -> list:
        r = await cliente.get(self.cfg.usgs_url)
        r.raise_for_status()
        return parsers.usgs_coleccion(r.json())


class EmscRestFallback(Poller):
    """Consulta EMSC por REST solo mientras el WebSocket lleva caído más de `emsc_fallback_tras_s`."""

    nombre = "emsc_rest"

    def __init__(self, cfg: Config, bus: Bus, ws: EmscWebSocket | None, cliente: httpx.AsyncClient | None = None):
        super().__init__(cfg, bus, cliente)
        self.ws = ws
        self.intervalo_s = cfg.emsc_rest_intervalo_s
        self._caido_desde: datetime | None = None

    def activo(self) -> bool:
        if self.ws is None:
            return True
        estado_ws = self.bus.estado_fuentes.get(self.ws.nombre, {}).get("estado")
        if estado_ws == "conectado":
            self._caido_desde = None
            return False
        ahora = datetime.now(timezone.utc)
        self._caido_desde = self._caido_desde or ahora
        return (ahora - self._caido_desde).total_seconds() >= self.cfg.emsc_fallback_tras_s

    async def consultar(self, cliente: httpx.AsyncClient) -> list:
        desde = datetime.now(timezone.utc) - timedelta(hours=1)
        r = await cliente.get(self.cfg.emsc_rest_url, params={
            "format": "json",
            "starttime": desde.strftime("%Y-%m-%dT%H:%M:%S"),
            "minmag": self.cfg.mag_min_mapa,
            "orderby": "time",
            "limit": 500,
        })
        if r.status_code == 204:  # FDSN: sin resultados
            return []
        r.raise_for_status()
        return parsers.emsc_coleccion(r.json())


class GlobalQuakeFdsnws(Poller):
    """Servidor FDSNWS-event incluido en GlobalQuake Server 0.11 (autoStartFDSNWSEventServer=true).

    No implementa búsqueda por radio ni `orderby`, así que se piden los sismos recientes y el bus
    filtra por cliente. Responde 204 cuando no hay sismos.
    """

    nombre = "globalquake"

    def __init__(self, cfg: Config, bus: Bus, cliente: httpx.AsyncClient | None = None):
        super().__init__(cfg, bus, cliente)
        self.intervalo_s = cfg.globalquake_intervalo_s

    async def consultar(self, cliente: httpx.AsyncClient) -> list:
        desde = datetime.now(timezone.utc) - timedelta(hours=1)
        r = await cliente.get(f"{self.cfg.globalquake_url}/fdsnws/event/1/query", params={
            "format": "geojson",
            "starttime": desde.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        if r.status_code == 204:
            return []
        r.raise_for_status()
        return parsers.emsc_coleccion(r.json(), fuente="globalquake")


def crear_fuentes(cfg: Config, bus: Bus) -> list[Fuente]:
    fuentes: list[Fuente] = []
    ws = None
    if "emsc_ws" in cfg.fuentes:
        ws = EmscWebSocket(cfg, bus)
        fuentes.append(ws)
    if "usgs" in cfg.fuentes:
        fuentes.append(UsgsPoller(cfg, bus))
    if "emsc_rest" in cfg.fuentes:
        fuentes.append(EmscRestFallback(cfg, bus, ws))
    if cfg.globalquake_url:
        fuentes.append(GlobalQuakeFdsnws(cfg, bus))
    desconocidas = set(cfg.fuentes) - {"emsc_ws", "usgs", "emsc_rest"}
    if desconocidas:
        log.warning("Fuentes desconocidas ignoradas: %s", ", ".join(sorted(desconocidas)))
    return fuentes
