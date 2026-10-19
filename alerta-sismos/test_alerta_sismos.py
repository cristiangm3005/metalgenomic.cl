"""Pruebas sin red: python3 -m unittest -v (desde la carpeta alerta-sismos)."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import alerta_sismos as a

AHORA = datetime.now(timezone.utc).replace(microsecond=0)

USGS = {
    "features": [
        {
            "id": "us7000abcd",
            "properties": {
                "mag": 5.2,
                "time": int(AHORA.timestamp() * 1000),
                "place": "40 km W of Copiapó, Chile",
                "magType": "mww",
                "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000abcd",
            },
            "geometry": {"coordinates": [-70.78, -27.40, 35.0]},
        },
        {"id": "sin_mag", "properties": {"mag": None, "time": 0}, "geometry": {"coordinates": [0, 0, 0]}},
    ]
}

EMSC = {
    "features": [
        {
            "id": "20261019_0000123",
            "properties": {
                "unid": "20261019_0000123",
                "time": (AHORA + timedelta(seconds=20)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "lat": -27.45,
                "lon": -70.75,
                "depth": 40.0,
                "mag": 5.0,
                "magtype": "ml",
                "flynn_region": "ATACAMA, CHILE",
            },
        }
    ]
}


def config(tmp: Path, reglas="100:3.5,300:4.5,2000:7.0") -> a.Config:
    return a.Config(lat=-27.3668, lon=-70.3314, lugar="Copiapó", reglas=a.parsear_reglas(reglas),
                    intervalo_s=60, ventana_min=60, estado=tmp / "estado.json", fuentes=["usgs", "emsc"])


class TestUtilidades(unittest.TestCase):
    def test_distancia_copiapo_santiago(self):
        d = a.distancia_km(-27.3668, -70.3314, -33.4489, -70.6693)
        self.assertAlmostEqual(d, 677, delta=10)

    def test_rumbo(self):
        self.assertEqual(a.rumbo(-27.37, -70.33, -33.45, -70.67), "S")
        self.assertEqual(a.rumbo(-27.37, -70.33, -27.40, -71.50), "O")

    def test_reglas(self):
        reglas = a.parsear_reglas("300:4.5, 100:3.5")
        self.assertEqual([r.radio_km for r in reglas], [100, 300])
        s = a.parse_usgs(USGS)[0]
        s.distancia_km, s.mag = 250, 4.0
        self.assertIsNone(a.regla_que_cumple(s, reglas))
        s.mag = 4.6
        self.assertEqual(a.regla_que_cumple(s, reglas).radio_km, 300)

    def test_reglas_vacias(self):
        with self.assertRaises(ValueError):
            a.parsear_reglas(" , ")


class TestFuentes(unittest.TestCase):
    def test_parse_usgs(self):
        sismos = a.parse_usgs(USGS)
        self.assertEqual(len(sismos), 1)
        s = sismos[0]
        self.assertEqual((s.id, s.mag, s.lat, s.lon, s.prof_km), ("usgs:us7000abcd", 5.2, -27.40, -70.78, 35.0))
        self.assertEqual(s.tiempo, AHORA)

    def test_parse_emsc(self):
        s = a.parse_emsc(EMSC)[0]
        self.assertEqual(s.id, "emsc:20261019_0000123")
        self.assertEqual(s.lugar, "Atacama, Chile")
        self.assertEqual(s.tiempo.tzinfo, timezone.utc)

    def test_urls(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = config(Path(d))
            self.assertIn("maxradiuskm=2000", a.url_usgs(cfg, AHORA))
            self.assertIn("minmagnitude=3.5", a.url_usgs(cfg, AHORA))
            self.assertIn("maxradius=17.986", a.url_emsc(cfg, AHORA))


class TestProcesar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = config(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def sismos(self):
        lista = a.parse_usgs(USGS) + a.parse_emsc(EMSC)
        for s in lista:
            s.distancia_km = a.distancia_km(self.cfg.lat, self.cfg.lon, s.lat, s.lon)
        return lista

    @mock.patch.object(a, "notificar")
    def test_mismo_sismo_en_dos_fuentes_avisa_una_vez(self, notificar):
        estado = a.Estado(self.cfg.estado)
        self.assertEqual(a.procesar(self.cfg, self.sismos(), estado), 1)
        # Una segunda pasada (o reinicio del programa) no repite la alerta.
        self.assertEqual(a.procesar(self.cfg, self.sismos(), a.Estado(self.cfg.estado)), 0)
        self.assertEqual(notificar.call_count, 1)

    @mock.patch.object(a, "notificar")
    def test_revision_de_magnitud_al_alza(self, notificar):
        estado = a.Estado(self.cfg.estado)
        a.procesar(self.cfg, self.sismos(), estado)
        revisado = self.sismos()[0]
        revisado.mag = 6.0
        self.assertEqual(a.procesar(self.cfg, [revisado], estado), 1)
        self.assertTrue(notificar.call_args[0][1].startswith("Actualización"))

    @mock.patch.object(a, "notificar")
    def test_lejano_y_chico_no_avisa(self, notificar):
        s = self.sismos()[0]
        s.lat, s.lon, s.mag = -33.45, -70.67, 5.0
        s.distancia_km = a.distancia_km(self.cfg.lat, self.cfg.lon, s.lat, s.lon)
        self.assertEqual(a.procesar(self.cfg, [s], a.Estado(self.cfg.estado)), 0)
        notificar.assert_not_called()

    def test_formato(self):
        titulo, cuerpo = a.formatear(self.sismos()[0], self.cfg)
        self.assertEqual(titulo, "Sismo M5.2 a 44 km de Copiapó")
        self.assertIn("al O de Copiapó", cuerpo)
        self.assertIn("Profundidad: 35 km", cuerpo)


if __name__ == "__main__":
    unittest.main()
