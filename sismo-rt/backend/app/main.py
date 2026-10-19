"""API en tiempo real de alertas sísmicas.

Ejecutar:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

from fastapi import FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from .bus import Bus, Suscriptor
from .config import Config
from .fuentes import crear_fuentes
from .fuentes.parsers import parse_tiempo
from .modelos import Filtro, Reporte
from .notificadores import NotificadorNtfy

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sismo.api")

HEARTBEAT_S = 15


# --- esquemas de entrada --------------------------------------------------------

class Suscripcion(BaseModel):
    """Mensaje que el cliente envía por WebSocket (al conectar y cada vez que cambia su GPS)."""

    tipo: str = "ubicacion"
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    radio_km: float | None = Field(default=None, gt=0, le=20000)
    mag_global: float | None = Field(default=None, ge=0, le=10)
    mag_min: float | None = Field(default=None, ge=-2, le=10)


class ReporteExterno(BaseModel):
    """Detección enviada por un detector propio (p. ej. un fork de GlobalQuake)."""

    id: str = Field(min_length=1, max_length=128)
    fuente: str = Field(default="globalquake", pattern=r"^[a-z0-9_\-]{1,32}$")
    tiempo: str | int = Field(description="Hora de origen: ISO 8601 (UTC) o epoch en ms")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    prof_km: float | None = Field(default=None, ge=-10, le=800)
    mag: float = Field(ge=-2, le=10)
    tipo_mag: str = ""
    lugar: str = ""


class Simulacion(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    mag: float = Field(default=6.5, ge=0, le=10)
    prof_km: float = Field(default=30, ge=0, le=700)
    segundos_atras: float = Field(default=0, ge=0, le=3600)
    lugar: str = "Sismo simulado"


# --- aplicación -----------------------------------------------------------------

def crear_app(cfg: Config | None = None) -> FastAPI:
    cfg = cfg or Config.desde_entorno()
    bus = Bus(cfg)

    @contextlib.asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        tareas = [asyncio.create_task(f.correr(), name=f.nombre) for f in crear_fuentes(cfg, bus)]
        ntfy = NotificadorNtfy.desde_config(cfg, bus)
        if ntfy:
            tareas.append(asyncio.create_task(ntfy.correr(), name="ntfy"))
        log.info("Fuentes activas: %s | ntfy: %s | ingesta: %s | simulación: %s",
                 ", ".join(cfg.fuentes) or "ninguna", "sí" if ntfy else "no",
                 "sí" if cfg.ingest_token else "no", "sí" if cfg.simulacion else "no")
        try:
            yield
        finally:
            for t in tareas:
                t.cancel()
            await asyncio.gather(*tareas, return_exceptions=True)

    app = FastAPI(title="Sismo RT", version="1.0.0", lifespan=ciclo_de_vida,
                  description="Alertas sísmicas personales en tiempo real (EMSC + USGS + GlobalQuake).")
    app.state.cfg = cfg
    app.state.bus = bus
    app.add_middleware(CORSMiddleware, allow_origins=list(cfg.cors_origenes),
                       allow_methods=["GET", "POST"], allow_headers=["*"])

    def filtro_de(lat, lon, radio_km=None, mag_global=None, mag_min=None) -> Filtro | None:
        if lat is None or lon is None:
            return None
        return Filtro.por_defecto(cfg, lat, lon, radio_km=radio_km, mag_global=mag_global, mag_min=mag_min)

    # --- REST ---------------------------------------------------------------

    @app.get("/api/salud")
    def salud():
        return {"ok": True, "eventos": len(bus.eventos), "clientes": len(bus.suscriptores),
                "fuentes": bus.estado_fuentes}

    @app.get("/api/config")
    def config_publica():
        return {"radio_km": cfg.radio_km, "mag_global": cfg.mag_global, "mag_alerta": cfg.mag_alerta,
                "mmi_alerta": cfg.mmi_alerta, "mag_min_mapa": cfg.mag_min_mapa, "vp_km_s": cfg.vp_km_s,
                "vs_km_s": cfg.vs_km_s, "simulacion": cfg.simulacion}

    @app.get("/api/eventos")
    def eventos(
        lat: float | None = Query(None, ge=-90, le=90),
        lon: float | None = Query(None, ge=-180, le=180),
        radio_km: float | None = Query(None, gt=0),
        mag_global: float | None = Query(None),
        mag_min: float | None = Query(None),
    ):
        """Eventos recientes; con lat/lon incluye distancia, intensidad y nivel para esa ubicación."""
        s = Suscriptor(cfg, filtro_de(lat, lon, radio_km, mag_global, mag_min))
        return bus.snapshot(s)

    @app.post("/api/ingest", status_code=202)
    def ingest(rep: ReporteExterno, authorization: str = Header(default="")):
        """Puerta de entrada para GlobalQuake u otro detector. Requiere `Authorization: Bearer <INGEST_TOKEN>`."""
        if not cfg.ingest_token:
            raise HTTPException(403, "Ingesta deshabilitada (define INGEST_TOKEN)")
        if not hmac.compare_digest(authorization.encode(), f"Bearer {cfg.ingest_token}".encode()):
            raise HTTPException(401, "Token inválido")
        if rep.fuente in ("usgs", "emsc"):
            raise HTTPException(422, "Ese nombre de fuente está reservado")
        try:
            tiempo = parse_tiempo(rep.tiempo)
        except (ValueError, OverflowError) as exc:
            raise HTTPException(422, f"tiempo inválido: {exc}") from exc
        ev = bus.recibir(Reporte(fuente=rep.fuente, id_fuente=rep.id, tiempo=tiempo, lat=rep.lat, lon=rep.lon,
                                 prof_km=rep.prof_km, mag=rep.mag, tipo_mag=rep.tipo_mag, lugar=rep.lugar))
        return {"aceptado": True, "evento": ev.id if ev else None}

    @app.post("/api/simular", status_code=202)
    def simular(sim: Simulacion):
        """Inyecta un sismo falso para probar el cliente. Solo con SIMULACION=true."""
        if not cfg.simulacion:
            raise HTTPException(403, "Simulación deshabilitada (SIMULACION=true para activarla)")
        ev = bus.recibir(Reporte(
            fuente="simulacion", id_fuente=uuid.uuid4().hex[:12],
            tiempo=datetime.now(timezone.utc) - timedelta(seconds=sim.segundos_atras),
            lat=sim.lat, lon=sim.lon, prof_km=sim.prof_km, mag=sim.mag, tipo_mag="sim", lugar=sim.lugar))
        return {"evento": ev.id if ev else None}

    # --- Server-Sent Events -------------------------------------------------

    @app.get("/api/stream")
    async def stream(
        request: Request,
        lat: float | None = Query(None, ge=-90, le=90),
        lon: float | None = Query(None, ge=-180, le=180),
        radio_km: float | None = Query(None, gt=0),
        mag_global: float | None = Query(None),
        mag_min: float | None = Query(None),
    ):
        """Flujo SSE. Ideal para clientes simples: `new EventSource('/api/stream?lat=..&lon=..')`."""
        s = Suscriptor(cfg, filtro_de(lat, lon, radio_km, mag_global, mag_min))
        return StreamingResponse(
            flujo_sse(bus, s, request.is_disconnected),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
        )

    # --- WebSocket ----------------------------------------------------------

    @app.websocket("/ws")
    async def websocket(ws: WebSocket):
        """Canal bidireccional: el cliente manda su ubicación (puede cambiar con el GPS) y recibe sismos."""
        await ws.accept()
        s = Suscriptor(cfg)
        bus.suscribir(s)

        async def recibir_del_cliente():
            while True:
                texto = await ws.receive_text()
                try:
                    datos = json.loads(texto)
                    if datos.get("tipo") == "ping":
                        s.enviar({"tipo": "pong"})
                        continue
                    sub = Suscripcion.model_validate(datos)
                except (ValueError, ValidationError) as exc:
                    s.enviar({"tipo": "error", "detalle": str(exc)[:300]})
                    continue
                s.filtro = filtro_de(sub.lat, sub.lon, sub.radio_km, sub.mag_global, sub.mag_min)
                s.enviar(bus.snapshot(s))

        async def enviar_al_cliente():
            await ws.send_json({"tipo": "hola", "fuentes": bus.estado_fuentes,
                                "mensaje": "Envía {tipo:'ubicacion', lat, lon} para recibir datos personalizados"})
            while True:
                await ws.send_json(await s.cola.get())

        tareas = [asyncio.create_task(recibir_del_cliente()), asyncio.create_task(enviar_al_cliente())]
        try:
            await asyncio.wait(tareas, return_when=asyncio.FIRST_COMPLETED)
        finally:
            bus.desuscribir(s)
            for t in tareas:
                t.cancel()
            for t in tareas:
                with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                    await t

    return app


async def flujo_sse(bus: Bus, s: Suscriptor, desconectado) -> AsyncIterator[str]:
    bus.suscribir(s)
    try:
        yield "retry: 3000\n\n"
        yield formato_sse(bus.snapshot(s))
        while True:
            try:
                msg = await asyncio.wait_for(s.cola.get(), timeout=HEARTBEAT_S)
            except asyncio.TimeoutError:
                if await desconectado():
                    break
                yield ": ping\n\n"  # mantiene viva la conexión a través de proxies
                continue
            yield formato_sse(msg)
    finally:
        bus.desuscribir(s)


def formato_sse(msg: dict) -> str:
    return f"event: {msg['tipo']}\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"


app = crear_app()
