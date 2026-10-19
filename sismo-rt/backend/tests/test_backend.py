"""Pruebas sin red externa: `pytest -q` desde sismo-rt/backend."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app import sismologia as sis
from app.bus import Bus, Suscriptor
from app.config import Config
from app.fuentes import EmscRestFallback, EmscWebSocket, UsgsPoller, parsers
from app.main import crear_app, flujo_sse
from app.modelos import Filtro, Reporte, evaluar

COPIAPO = (-27.3668, -70.3314)
AHORA = datetime.now(timezone.utc).replace(microsecond=0)


def cfg(**extra) -> Config:
    base = dict(fuentes=(), simulacion=True, ingest_token="secreto")
    base.update(extra)
    return Config(**base)


def rep(fuente="usgs", id_="a1", mag=5.5, lat=-27.40, lon=-70.80, prof=30.0, t=AHORA) -> Reporte:
    return Reporte(fuente=fuente, id_fuente=id_, tiempo=t, lat=lat, lon=lon, prof_km=prof, mag=mag)


# --- sismología -------------------------------------------------------------------

def test_haversine_copiapo_santiago():
    assert sis.distancia_km(*COPIAPO, -33.4489, -70.6693) == pytest.approx(677, abs=10)


def test_mmi_decrece_con_distancia_y_crece_con_magnitud():
    assert sis.mmi_allen2012(6, 20) > sis.mmi_allen2012(6, 200) > sis.mmi_allen2012(6, 800)
    assert sis.mmi_allen2012(7, 100) > sis.mmi_allen2012(5, 100)
    # Orden de magnitud razonable: M7 a 50 km ~ VI-VII.
    assert 6 <= sis.mmi_allen2012(7, 50) <= 7.5
    assert 1 <= sis.mmi_allen2012(2, 3000) and sis.mmi_allen2012(9.5, 1) <= 10


def test_pga_monotona_y_razonable():
    assert sis.pga_desde_mmi(3) < sis.pga_desde_mmi(5) < sis.pga_desde_mmi(8)
    assert 0.05 < sis.pga_desde_mmi(6) < 0.2  # MMI VI ~ 0.1 g


def test_llegada_ondas():
    p, s = sis.tiempos_llegada(AHORA, 130, 6.5, 3.25)
    assert (p - AHORA).total_seconds() == pytest.approx(20)
    assert (s - AHORA).total_seconds() == pytest.approx(40)


def test_evaluar_niveles():
    c = cfg()
    bus = Bus(c)
    filtro = Filtro.por_defecto(c, *COPIAPO)
    cerca = evaluar(bus.recibir(rep(mag=5.5)), filtro, c)
    assert cerca["nivel"] == "alerta" and cerca["motivo"] == "cerca" and cerca["rumbo"] == "O"
    chico = evaluar(bus.recibir(rep(id_="b", mag=3.0, t=AHORA - timedelta(hours=2))), filtro, c)
    assert chico["nivel"] == "info"
    lejos_grande = evaluar(bus.recibir(rep(id_="c", mag=7.2, lat=38.3, lon=142.4, t=AHORA - timedelta(hours=3))),
                           filtro, c)
    assert lejos_grande["motivo"] == "magnitud" and lejos_grande["nivel"] == "info"  # no se siente en Copiapó
    lejos_chico = evaluar(bus.recibir(rep(id_="d", mag=5.0, lat=38.3, lon=142.4, t=AHORA - timedelta(hours=4))),
                          filtro, c)
    assert lejos_chico["nivel"] is None


# --- parsers ----------------------------------------------------------------------

def test_parse_emsc_ws():
    msg = {"action": "create", "data": {"type": "Feature", "id": "20261019_0000123", "properties": {
        "unid": "20261019_0000123", "time": "2026-10-19T12:00:00.5Z", "lat": -27.45, "lon": -70.75,
        "depth": 40.0, "mag": 5.0, "magtype": "ml", "flynn_region": "ATACAMA, CHILE", "evtype": "ke"}}}
    r = parsers.emsc_ws_mensaje(msg)
    assert (r.fuente, r.id_fuente, r.lugar, r.prof_km) == ("emsc", "20261019_0000123", "Atacama, Chile", 40.0)
    assert r.tiempo.tzinfo == timezone.utc
    assert parsers.emsc_ws_mensaje({"action": "delete", "data": msg["data"]}) is None
    msg["data"]["properties"]["evtype"] = "qb"
    assert parsers.emsc_ws_mensaje(msg) is None


def test_parse_usgs():
    datos = {"features": [
        {"id": "us1", "properties": {"mag": 4.8, "time": 1760000000000, "place": "X", "magType": "mb",
                                      "url": "u", "type": "earthquake"},
         "geometry": {"coordinates": [-70.8, -27.4, 33.0]}},
        {"id": "us2", "properties": {"mag": 2.0, "time": 1760000000000, "type": "quarry blast"},
         "geometry": {"coordinates": [0, 0, 0]}},
        {"id": "us3", "properties": {"mag": None, "time": 1}, "geometry": {"coordinates": [0, 0]}},
    ]}
    rs = parsers.usgs_coleccion(datos)
    assert [r.id_fuente for r in rs] == ["us1"]
    assert rs[0].tiempo == datetime.fromtimestamp(1760000000, tz=timezone.utc)


# --- bus ------------------------------------------------------------------------

async def test_fusion_entre_fuentes_y_notificacion_unica():
    c = cfg()
    bus = Bus(c)
    s = Suscriptor(c, Filtro.por_defecto(c, *COPIAPO))
    bus.suscribir(s)

    gq = bus.recibir(rep(fuente="globalquake", id_="gq1", mag=5.1, lat=-27.5, lon=-70.9))
    m1 = s.cola.get_nowait()
    assert m1["accion"] == "nuevo" and m1["notificar"] and not m1["evento"]["confirmado"]

    # EMSC confirma 20 s después con otro ID y ubicación algo distinta: mismo evento.
    assert bus.recibir(rep(fuente="emsc", id_="e1", mag=5.2, t=AHORA + timedelta(seconds=20))) is gq
    m2 = s.cola.get_nowait()
    assert m2["accion"] == "actualizacion" and m2["evento"]["confirmado"] and not m2["notificar"]
    assert m2["evento"]["fuentes"] == ["emsc", "globalquake"]

    # Reenvío idéntico de EMSC: nada que difundir.
    assert bus.recibir(rep(fuente="emsc", id_="e1", mag=5.2, t=AHORA + timedelta(seconds=20))) is None
    assert s.cola.empty()
    assert len(bus.eventos) == 1


async def test_escala_de_info_a_alerta_vuelve_a_notificar():
    c = cfg()
    bus = Bus(c)
    s = Suscriptor(c, Filtro.por_defecto(c, *COPIAPO))
    bus.suscribir(s)
    bus.recibir(rep(fuente="emsc", id_="e", mag=3.6))
    assert s.cola.get_nowait()["usuario"]["nivel"] == "info"
    bus.recibir(rep(fuente="emsc", id_="e", mag=4.9))
    m = s.cola.get_nowait()
    assert m["usuario"]["nivel"] == "alerta" and m["notificar"]


async def test_eventos_viejos_no_notifican_y_cola_llena_no_bloquea():
    c = cfg()
    bus = Bus(c)
    s = Suscriptor(c, Filtro.por_defecto(c, *COPIAPO), max_cola=3)
    bus.suscribir(s)
    bus.recibir(rep(id_="viejo", t=AHORA - timedelta(hours=2)))
    assert s.cola.get_nowait()["notificar"] is False
    for i in range(10):
        bus.recibir(rep(id_=f"x{i}", lat=-20 - i * 3, t=AHORA - timedelta(minutes=i * 5)))
    assert s.cola.qsize() == 3


def test_purga_por_cantidad():
    c = cfg(max_eventos=5)
    bus = Bus(c)
    for i in range(12):
        bus.recibir(rep(id_=f"x{i}", lat=-10 - i * 3, t=AHORA - timedelta(minutes=i)))
    assert len(bus.eventos) <= 6


# --- API ------------------------------------------------------------------------

def test_websocket_ubicacion_y_alerta():
    app = crear_app(cfg())
    with TestClient(app) as cli, cli.websocket_connect("/ws") as ws:
        assert ws.receive_json()["tipo"] == "hola"
        ws.send_json({"tipo": "ubicacion", "lat": COPIAPO[0], "lon": COPIAPO[1]})
        assert ws.receive_json()["tipo"] == "snapshot"
        r = cli.post("/api/simular", json={"lat": -27.6, "lon": -70.9, "mag": 6.8, "prof_km": 25})
        assert r.status_code == 202
        msg = ws.receive_json()
        assert msg["tipo"] == "sismo" and msg["notificar"]
        u = msg["usuario"]
        assert u["nivel"] == "alerta" and u["mmi"] >= 5 and u["s_restante_s"] > 0
        assert u["llegada_s_ms"] > u["llegada_p_ms"]
        ws.send_text("no es json")
        assert ws.receive_json()["tipo"] == "error"


def test_ingest_globalquake_requiere_token():
    app = crear_app(cfg())
    body = {"id": "gq-1", "tiempo": AHORA.isoformat(), "lat": -27.5, "lon": -70.5, "mag": 4.4, "prof_km": 10}
    with TestClient(app) as cli:
        assert cli.post("/api/ingest", json=body).status_code == 401
        assert cli.post("/api/ingest", json=body, headers={"Authorization": "Bearer malo"}).status_code == 401
        r = cli.post("/api/ingest", json=body, headers={"Authorization": "Bearer secreto"})
        assert r.status_code == 202 and r.json()["evento"] == "globalquake:gq-1"
        evs = cli.get("/api/eventos", params={"lat": COPIAPO[0], "lon": COPIAPO[1]}).json()["eventos"]
        assert evs[0]["evento"]["confirmado"] is False and evs[0]["usuario"]["distancia_km"] < 30
        assert cli.post("/api/ingest", json={**body, "fuente": "usgs"},
                        headers={"Authorization": "Bearer secreto"}).status_code == 422


def test_ingest_y_simulacion_deshabilitados_por_defecto():
    app = crear_app(cfg(ingest_token="", simulacion=False))
    with TestClient(app) as cli:
        assert cli.post("/api/simular", json={"lat": 0, "lon": 0}).status_code == 403
        assert cli.post("/api/ingest", json={"id": "x", "tiempo": 0, "lat": 0, "lon": 0, "mag": 1}).status_code == 403
        assert cli.get("/api/salud").json()["ok"] is True


async def test_flujo_sse():
    c = cfg()
    bus = Bus(c)
    s = Suscriptor(c, Filtro.por_defecto(c, *COPIAPO))

    async def nunca_desconecta():
        return False

    gen = flujo_sse(bus, s, nunca_desconecta)
    assert (await gen.__anext__()).startswith("retry:")
    assert (await gen.__anext__()).startswith("event: snapshot\n")
    bus.recibir(rep(mag=6.0))
    trozo = await gen.__anext__()
    assert trozo.startswith("event: sismo\ndata: ")
    assert json.loads(trozo.split("data: ", 1)[1])["usuario"]["nivel"] == "alerta"
    await gen.aclose()
    assert s not in bus.suscriptores


# --- fuentes (con servidores falsos, sin internet) --------------------------------

USGS_GEOJSON = {"features": [{"id": "us9", "properties": {"mag": 5.0, "time": int(AHORA.timestamp() * 1000),
                                                          "place": "Chile", "type": "earthquake"},
                              "geometry": {"coordinates": [-70.8, -27.4, 30]}}]}


async def test_usgs_poller_con_transporte_falso():
    c = cfg(usgs_intervalo_s=0.01)
    bus = Bus(c)
    cliente = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=USGS_GEOJSON)))
    tarea = asyncio.create_task(UsgsPoller(c, bus, cliente).correr())
    await asyncio.sleep(0.1)
    tarea.cancel()
    await asyncio.gather(tarea, return_exceptions=True)
    assert list(bus.eventos) == ["usgs:us9"]
    assert bus.estado_fuentes["usgs"]["estado"] == "ok"
    await cliente.aclose()


async def test_emsc_rest_solo_se_activa_si_el_websocket_cae():
    c = cfg(emsc_fallback_tras_s=0)
    bus = Bus(c)
    ws = EmscWebSocket(c, bus)
    fb = EmscRestFallback(c, bus, ws)
    bus.actualizar_fuente("emsc_ws", estado="conectado")
    assert fb.activo() is False
    bus.actualizar_fuente("emsc_ws", estado="desconectado")
    assert fb.activo() is True


async def test_emsc_websocket_contra_servidor_local():
    import websockets

    msg = {"action": "create", "data": {"id": "w1", "properties": {
        "unid": "w1", "time": AHORA.isoformat(), "lat": -27.4, "lon": -70.8, "depth": 20, "mag": 4.7,
        "magtype": "mw", "flynn_region": "ATACAMA, CHILE"}}}

    async def servidor(conexion):
        await conexion.send(json.dumps(msg))
        await asyncio.sleep(1)

    async with websockets.serve(servidor, "127.0.0.1", 0) as srv:
        puerto = srv.sockets[0].getsockname()[1]
        c = cfg(emsc_ws_url=f"ws://127.0.0.1:{puerto}")
        bus = Bus(c)
        tarea = asyncio.create_task(EmscWebSocket(c, bus).correr())
        for _ in range(50):
            await asyncio.sleep(0.02)
            if bus.eventos:
                break
        tarea.cancel()
        await asyncio.gather(tarea, return_exceptions=True)
    assert list(bus.eventos) == ["emsc:w1"]


def test_mmi_valores_de_referencia_openquake():
    # AllenEtAl2012Rhypo: c0 + c1·M + c2·ln(√(R² + (m1 + m2·e^(M-5))²)) [+ c4·ln(R/50) si R > 50]
    assert sis.mmi_allen2012(7.0, 50) == pytest.approx(6.537, abs=0.005)
    assert sis.mmi_allen2012(7.0, 200) == pytest.approx(4.757, abs=0.005)
    assert sis.mmi_allen2012(5.0, 10) == pytest.approx(5.974, abs=0.005)


def test_pga_valores_de_referencia_worden2012():
    # MMI = 1.78 + 1.55·log10(PGA cm/s²) y MMI = -1.60 + 3.70·log10(PGA) (esi_shakelib wgrw12)
    assert sis.pga_desde_mmi(1.78 + 1.55 * 1.0) * 980.665 == pytest.approx(10, rel=1e-6)
    assert sis.pga_desde_mmi(-1.60 + 3.70 * 2.0) * 980.665 == pytest.approx(100, rel=1e-6)


# Respuesta real de GlobalQuake Server 0.11 (ArchivedQuake.getGeoJSON en la rama 0.11.0).
GQ_GEOJSON = {"type": "FeatureCollection", "features": [{
    "type": "Feature", "id": "6f1c2b9a-0000-4000-8000-000000000001",
    "properties": {"lastupdate": 1792444000000, "magtype": "gqm", "evtype": "earthquake", "lon": -70.9,
                   "auth": "GlobalQuake", "lat": -27.5, "depth": 32.5,
                   "unid": "6f1c2b9a-0000-4000-8000-000000000001", "mag": 5.6,
                   "time": AHORA.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                   "source_id": "GlobalQuake_6f1c2b9a-0000-4000-8000-000000000001",
                   "source_catalog": "GlobalQuake", "flynn_region": "Atacama, Chile"},
    "geometry": {"type": "Point", "coordinates": [-70.9, -27.5, -32.5]}}]}


async def test_globalquake_fdsnws():
    from app.fuentes import GlobalQuakeFdsnws

    pedidas = []

    def responder(req):
        pedidas.append(req.url)
        return httpx.Response(200, json=GQ_GEOJSON)

    c = cfg(globalquake_url="http://gq:8080", globalquake_intervalo_s=0.01)
    bus = Bus(c)
    cliente = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    tarea = asyncio.create_task(GlobalQuakeFdsnws(c, bus, cliente).correr())
    await asyncio.sleep(0.1)
    tarea.cancel()
    await asyncio.gather(tarea, return_exceptions=True)
    await cliente.aclose()
    ev = bus.eventos["globalquake:6f1c2b9a-0000-4000-8000-000000000001"]
    assert ev.principal.prof_km == 32.5 and not ev.confirmado
    assert pedidas[0].path == "/fdsnws/event/1/query" and pedidas[0].params["format"] == "geojson"
