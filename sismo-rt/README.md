# Sismo RT — alertas sísmicas personales en tiempo real

Backend en **Python + FastAPI** que recibe sismos en tiempo real (WebSocket de EMSC, detecciones
de GlobalQuake vía hook) con respaldo de USGS y EMSC REST, fusiona los reportes y los reparte por
**WebSocket** o **SSE** a cada cliente con cálculos personalizados para su ubicación:

- distancia (Haversine) y dirección al epicentro,
- intensidad de Mercalli Modificada estimada (Allen et al. 2012) y PGA aproximada,
- hora de llegada de las ondas P y S y segundos restantes para la onda S,
- nivel `info` / `alerta` y bandera `notificar` (sin spam en actualizaciones).

Opcionalmente envía push al celular con **ntfy** para una ubicación fija.

> ⚠️ **No reemplaza al SAE de SENAPRED ni al CSN.** Los catálogos (EMSC/USGS) publican con
> minutos de retraso, y GlobalQuake es experimental. Lee los
> [límites del sistema](docs/ARQUITECTURA.md#límites-honestos-del-sistema).

## Documentación

- [Arquitectura y flujo de datos](docs/ARQUITECTURA.md)
- [Protocolo WebSocket / SSE / REST](docs/PROTOCOLO.md)
- [Integración con GlobalQuake](docs/GLOBALQUAKE.md)

## Estructura

```
sismo-rt/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI: /ws, /api/stream (SSE), /api/eventos, /api/ingest, /api/simular
│   │   ├── bus.py            # fusión de reportes, deduplicación y difusión a clientes
│   │   ├── modelos.py        # Reporte, Evento, Filtro y evaluación por usuario
│   │   ├── sismologia.py     # Haversine, MMI, PGA, ondas P/S
│   │   ├── notificadores.py  # push ntfy
│   │   ├── config.py         # variables de entorno
│   │   └── fuentes/          # EMSC WebSocket, USGS, EMSC REST + parsers
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
└── docs/
```

## Ejecutar localmente

Requisitos: **Python 3.10+**.

```bash
cd sismo-rt/backend
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # ajusta umbrales, token de ingesta, ntfy...
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

En los logs verás `Fuente emsc_ws -> conectado` y, cada 30 s, `Fuente usgs -> ok`.
Estado en vivo: <http://localhost:8000/api/salud> · API interactiva: <http://localhost:8000/docs>.

### Probar sin esperar un sismo real

Con `SIMULACION=true` en `.env`:

```bash
# Terminal 1: escuchar el flujo SSE como lo haría el navegador (ubicación: Copiapó)
curl -N "http://localhost:8000/api/stream?lat=-27.3668&lon=-70.3314"

# Terminal 2: simular un M7.1 frente a la costa
curl -X POST http://localhost:8000/api/simular -H "Content-Type: application/json" \
     -d '{"lat": -27.2, "lon": -71.2, "mag": 7.1, "prof_km": 35}'
```

La terminal 1 recibe al instante un `event: sismo` con `"nivel": "alerta"`, la intensidad estimada
y la cuenta regresiva de la onda S.

Por WebSocket (con [websocat](https://github.com/vi/websocat)):

```bash
websocat ws://localhost:8000/ws
{"tipo":"ubicacion","lat":-27.3668,"lon":-70.3314}
```

### Push al celular (ntfy)

1. Instala la app **ntfy** (Android/iOS) y suscríbete a un tema difícil de adivinar.
2. En `.env`: `NTFY_TOPIC=<tu-tema>` y `CASA_LAT` / `CASA_LON` / `CASA_NOMBRE`.
3. Reinicia el backend. Las alertas fuertes llegan con prioridad `high`/`urgent`.

### Pruebas

```bash
pip install -r requirements-dev.txt
pytest -q
```

Las pruebas no usan internet: incluyen un servidor WebSocket local que imita a EMSC y un
transporte HTTP falso para USGS.

## Producción (resumen)

- Ejecuta con un solo worker (`uvicorn ... --workers 1`): el bus vive en memoria.
- Detrás de Nginx/Caddy habilita WebSocket (`Upgrade`) y desactiva el buffering para SSE.
- Define `INGEST_TOKEN`, `SIMULACION=false` y restringe `CORS_ORIGENES` a tu dominio.

## Próximo paso

Cliente web (Leaflet) con mapa en vivo, círculos de onda P/S animados, contador de onda S,
geolocalización GPS o ubicación fija y notificaciones nativas con sonido según el nivel.
