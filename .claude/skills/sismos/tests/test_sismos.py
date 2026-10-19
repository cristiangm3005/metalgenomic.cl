"""Pruebas sin red: python3 -m unittest discover -s .claude/skills/sismos/tests -v"""

import io
import json
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import sismos as s  # noqa: E402

AHORA = datetime.now(timezone.utc).replace(microsecond=0)


def cfg(tmp, **kw):
    base = dict(lat=-27.3668, lon=-70.3314, lugar="Copiapó", radio_km=500, mag_global=6.0, mag_min=3.0,
                intervalo_s=0.05, rt_url="", estado=Path(tmp) / "estado.json")
    base.update(kw)
    return s.Config(**base)


USGS = {"features": [
    {"id": "us1", "properties": {"mag": 5.4, "time": int(AHORA.timestamp() * 1000), "place": "40 km W of Copiapó",
                                 "type": "earthquake", "url": "https://usgs/us1"},
     "geometry": {"coordinates": [-70.78, -27.40, 35.0]}},
    {"id": "us2", "properties": {"mag": 4.0, "time": int(AHORA.timestamp() * 1000), "type": "quarry blast"},
     "geometry": {"coordinates": [-70.5, -27.4, 0]}},
]}
EMSC = {"features": [
    {"id": "e1", "properties": {"unid": "e1", "time": (AHORA + timedelta(seconds=15)).isoformat(), "lat": -27.45,
                                "lon": -70.75, "depth": 40, "mag": 5.2, "flynn_region": "ATACAMA, CHILE"}},
    {"id": "e2", "properties": {"unid": "e2", "time": AHORA.isoformat(), "lat": 35.6, "lon": 139.7, "depth": 10,
                                "mag": 4.5, "flynn_region": "NEAR COAST OF HONSHU, JAPAN"}},
]}


class TestCalculos(unittest.TestCase):
    def test_distancia_y_rumbo(self):
        self.assertAlmostEqual(s.distancia_km(-27.3668, -70.3314, -33.4489, -70.6693), 677, delta=10)
        self.assertEqual(s.rumbo(-27.37, -70.33, -27.40, -71.5), "O")

    def test_mmi(self):
        self.assertGreater(s.mmi_estimada(6, 20, 10), s.mmi_estimada(6, 300, 10))
        self.assertTrue(6 <= s.mmi_estimada(7, 50, 0) <= 7.5)


class TestFuentes(unittest.TestCase):
    def test_parsers_y_fusion(self):
        u, e = s.parse_usgs(USGS), s.parse_emsc(EMSC)
        self.assertEqual([x.id for x in u], ["us1"])  # descarta voladura de cantera
        fus = s.fusionar(u + e)
        self.assertEqual(len(fus), 2)
        chile = next(x for x in fus if x.lat < 0)
        self.assertEqual((chile.fuente, chile.fuentes), ("usgs", {"usgs", "emsc"}))

    def test_niveles(self):
        with tempfile.TemporaryDirectory() as d:
            c = cfg(d)
            chile, japon = s.parse_usgs(USGS)[0], s.parse_emsc(EMSC)[1]
            self.assertEqual(chile.evaluar(c)["nivel"], "ALERTA")
            self.assertIsNone(japon.evaluar(c)["nivel"])  # lejos y M<6
            japon.mag = 7.5
            self.assertEqual(japon.evaluar(c)["nivel"], "INFO")  # grande, pero no se siente aquí


class TestAvisos(unittest.TestCase):
    def test_no_repite_entre_reinicios_y_avisa_si_sube(self):
        with tempfile.TemporaryDirectory() as d:
            c = cfg(d)
            sismo = s.parse_emsc(EMSC)[0]
            self.assertIn("nivel=ALERTA", s.procesar(sismo, c, s.Memoria(c.estado), 30))
            # Otro proceso (monitor rearmado) y otra fuente con el mismo sismo: silencio.
            self.assertIsNone(s.procesar(s.parse_usgs(USGS)[0], c, s.Memoria(c.estado), 30))
            sismo.mag = 6.1
            self.assertIn("(actualización)", s.procesar(sismo, c, s.Memoria(c.estado), 30))

    def test_viejo_no_avisa(self):
        with tempfile.TemporaryDirectory() as d:
            c = cfg(d)
            sismo = s.parse_emsc(EMSC)[0]
            sismo.tiempo -= timedelta(hours=2)
            self.assertIsNone(s.procesar(sismo, c, s.Memoria(c.estado), 30))

    def test_estados_solo_en_cambios(self):
        out = io.StringIO()
        with redirect_stdout(out):
            e = s.Estados()
            e.marcar("usgs", True)
            e.marcar("usgs", True)
            e.marcar("usgs", False, "timeout")
            e.marcar("usgs", False, "timeout")
            e.marcar("usgs", True)
        self.assertEqual(out.getvalue().splitlines(),
                         ["ESTADO fuente=usgs CAIDA | timeout", "ESTADO fuente=usgs RECUPERADA"])

    def test_modo_ahora_con_fuentes_simuladas(self):
        def falso(url, params, timeout=20):
            datos = USGS if "usgs" in url else EMSC
            return datos if "lat" in params or "latitude" in params else {"features": []}

        with tempfile.TemporaryDirectory() as d, mock.patch.object(s, "get_json", falso):
            out = io.StringIO()
            with redirect_stdout(out):
                rc = s.ahora(cfg(d), 24, como_json=True)
            datos = json.loads(out.getvalue())
            self.assertEqual(rc, 0)
            self.assertEqual(len(datos), 1)
            self.assertEqual(datos[0]["nivel"], "ALERTA")
            self.assertEqual(datos[0]["fuentes"], ["emsc", "usgs"])

    def test_modo_ahora_sin_red(self):
        def falla(*a, **k):
            raise s.urllib.error.URLError("sin red")

        with tempfile.TemporaryDirectory() as d, mock.patch.object(s, "get_json", falla):
            with redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
                self.assertEqual(s.ahora(cfg(d), 1, como_json=False), 2)


class TestSismoRT(unittest.TestCase):
    """El vigilante escucha el flujo SSE de un backend sismo-rt falso."""

    def test_sse(self):
        evento = {"tipo": "sismo", "accion": "nuevo", "notificar": True, "evento": {
            "id": "globalquake:gq1", "tiempo": AHORA.isoformat(), "lat": -27.6, "lon": -70.9, "prof_km": 25,
            "mag": 6.2, "lugar": "Atacama", "url": "", "fuente_principal": "globalquake",
            "fuentes": ["globalquake"], "confirmado": False}}

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(b"event: snapshot\ndata: {}\n\n")
                self.wfile.write(f"event: sismo\ndata: {json.dumps(evento)}\n\n".encode())
                self.wfile.flush()

            def log_message(self, *a):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        lineas = []
        with tempfile.TemporaryDirectory() as d, mock.patch.object(s, "emitir", lineas.append), \
                mock.patch.dict("os.environ", {"NO_PROXY": "127.0.0.1"}):
            c = cfg(d, rt_url=f"http://127.0.0.1:{srv.server_address[1]}")
            ok = threading.Event()
            threading.Thread(target=s.escuchar_sse, args=(c, s.Memoria(c.estado), s.Estados(), ok, 30),
                             daemon=True).start()
            for _ in range(100):
                if lineas:
                    break
                threading.Event().wait(0.02)
        srv.shutdown()
        self.assertTrue(lineas and "nivel=ALERTA" in lineas[0] and "SIN_CONFIRMAR" in lineas[0], lineas)


if __name__ == "__main__":
    unittest.main()


class TestReferencias(unittest.TestCase):
    def test_mmi_openquake(self):
        # AllenEtAl2012Rhypo (OpenQuake). Profundidad 0 => distancia hipocentral = epicentral.
        self.assertAlmostEqual(s.mmi_estimada(7.0, 50, 0), 6.537, delta=0.005)
        self.assertAlmostEqual(s.mmi_estimada(7.0, 200, 0), 4.757, delta=0.005)
        self.assertAlmostEqual(s.mmi_estimada(5.0, 10, 0), 5.974, delta=0.005)


class TestGlobalQuake(unittest.TestCase):
    """Servidor falso con la misma respuesta que GlobalQuake Server 0.11 (FDSNWS-event)."""

    def test_fdsnws(self):
        geo = {"type": "FeatureCollection", "features": [{
            "type": "Feature", "id": "uuid-1",
            "properties": {"magtype": "gqm", "evtype": "earthquake", "lon": -70.9, "auth": "GlobalQuake",
                           "lat": -27.5, "depth": 32.5, "unid": "uuid-1", "mag": 5.6,
                           "time": AHORA.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "flynn_region": "Atacama, Chile"},
            "geometry": {"type": "Point", "coordinates": [-70.9, -27.5, -32.5]}}]}
        rutas = []

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                rutas.append(self.path)
                cuerpo = json.dumps(geo).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)

            def log_message(self, *a):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as d, mock.patch.dict("os.environ", {"NO_PROXY": "127.0.0.1"}):
                c = cfg(d, gq_url=f"http://127.0.0.1:{srv.server_address[1]}")
                sismos = s.consultar_gq(c, AHORA - timedelta(minutes=30))
                texto = s.procesar(sismos[0], c, s.Memoria(c.estado), 30)
        finally:
            srv.shutdown()
        self.assertTrue(rutas[0].startswith("/fdsnws/event/1/query?format=geojson"))
        self.assertIn("nivel=ALERTA", texto)
        self.assertIn("fuentes=globalquake SIN_CONFIRMAR", texto)
