# Protocolo cliente ↔ servidor

Todos los mensajes son JSON. Las horas van en ISO 8601 UTC (`tiempo`) y en epoch ms (`*_ms`)
para que el cliente calcule cuentas regresivas sin parsear fechas.

## WebSocket `/ws`

**Cliente → servidor**

```json
{"tipo": "ubicacion", "lat": -27.3668, "lon": -70.3314, "radio_km": 500, "mag_global": 6.0, "mag_min": 2.5}
```

`radio_km`, `mag_global` y `mag_min` son opcionales (si faltan se usan los del servidor).
Se puede reenviar en cualquier momento (p. ej. cuando cambia el GPS); el servidor responde
con un `snapshot` recalculado. También acepta `{"tipo": "ping"}` → `{"tipo": "pong"}`.

**Servidor → cliente**

| `tipo` | Cuándo | Contenido |
|---|---|---|
| `hola` | Al conectar | `fuentes` |
| `snapshot` | Tras cada `ubicacion` | `eventos: [{evento, usuario}]` (más reciente primero), `fuentes` |
| `sismo` | Sismo nuevo o actualizado | `accion` (`nuevo`/`actualizacion`), `evento`, `usuario`, `notificar` |
| `fuentes` | Cambia el estado de una fuente | `fuentes` |
| `error` | Mensaje inválido | `detalle` |

## SSE `/api/stream?lat=..&lon=..[&radio_km=..&mag_global=..&mag_min=..]`

Mismos mensajes, como eventos con nombre (`event: snapshot`, `event: sismo`, `event: fuentes`)
y `: ping` cada 15 s.

```js
const es = new EventSource(`/api/stream?lat=${lat}&lon=${lon}`);
es.addEventListener("sismo", (e) => {
  const m = JSON.parse(e.data);
  if (m.notificar) alertar(m);
});
```

## Mensaje `sismo`

```json
{
  "tipo": "sismo",
  "accion": "nuevo",
  "notificar": true,
  "evento": {
    "id": "emsc:20261019_0000123", "version": 1,
    "tiempo": "2026-10-19T12:00:00.500Z", "tiempo_ms": 1792411200500,
    "lat": -27.45, "lon": -70.75, "prof_km": 40.0,
    "mag": 5.2, "tipo_mag": "mw", "lugar": "Atacama, Chile", "url": "https://...",
    "fuente_principal": "emsc", "fuentes": ["emsc", "usgs"], "confirmado": true,
    "detectado": "2026-10-19T12:02:10.120Z", "latencia_s": 129.6
  },
  "usuario": {
    "distancia_km": 42.3, "distancia_hipocentral_km": 58.4, "rumbo": "O",
    "mmi": 5.4, "mmi_romano": "V", "mmi_descripcion": "Moderado", "pga_g": 0.0391,
    "llegada_p_ms": 1792411209485, "llegada_s_ms": 1792411216073, "s_restante_s": -114.0,
    "relevante": true, "motivo": "cerca", "nivel": "alerta", "reciente": true
  }
}
```

- `usuario` es `null` si el cliente aún no envió su ubicación.
- `notificar` es `true` solo la primera vez que el evento es relevante para ese cliente o cuando
  sube de nivel (`info` → `alerta`), y nunca si el sismo tiene más de `MAX_EDAD_ALERTA_MIN`.
- `s_restante_s` negativo significa que la onda S ya pasó por tu ubicación.

## REST

| Método | Ruta | Uso |
|---|---|---|
| GET | `/api/salud` | Estado de fuentes, número de eventos y clientes |
| GET | `/api/config` | Parámetros públicos (umbrales, velocidades de onda) |
| GET | `/api/eventos?lat=..&lon=..` | Igual que `snapshot`, para carga inicial sin socket |
| POST | `/api/ingest` | Detecciones de GlobalQuake u otro detector (`Authorization: Bearer <INGEST_TOKEN>`) |
| POST | `/api/simular` | Sismo falso para pruebas (solo con `SIMULACION=true`) |

Documentación interactiva (OpenAPI): `http://localhost:8000/docs`.
