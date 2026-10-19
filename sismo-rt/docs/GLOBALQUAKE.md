# Integración con GlobalQuake

[GlobalQuake](https://github.com/xspanger3770/GlobalQuake) detecta sismos en segundos procesando en vivo
datos de estaciones sísmicas (SeedLink). Es la única pieza de este sistema que puede avisar **antes**
de que lleguen las ondas a lugares algo alejados del epicentro.

> **Estado del proyecto (verificado en octubre de 2026):** el repositorio público está **descontinuado**.
> Desde la versión 1.0.0 el desarrollo continúa como proyecto privado y propietario en
> <https://globalquake.net/>. El código abierto (licencia MIT) sigue disponible en las ramas antiguas
> (`0.10.2`, `0.11.0`, `develop`). Todo lo de abajo se verificó contra la rama **`0.11.0`**.
>
> Sus propios autores advierten que es experimental, que debe usarse "solo con fines de entretenimiento"
> y que los sismos M6+ suelen generar detecciones falsas o duplicadas. Por eso sus eventos llegan aquí
> marcados `confirmado: false` hasta que USGS o EMSC los confirman.

## Opción A (recomendada): servidor FDSNWS-event incluido en GlobalQuake Server

GlobalQuake Server 0.11 trae un servidor HTTP con la API estándar **FDSNWS-event**
(`gqserver/fdsnws_event/FdsnwsEventsHTTPServer.java`). No requiere modificar código.

1. En la configuración de GlobalQuake Server (archivo de settings) activa:
   ```properties
   autoStartFDSNWSEventServer=true
   FDSNWSEventIP=localhost
   FDSNWSEventPort=8080
   ```
   Por defecto viene apagado (`false`), en `localhost:8080`.
2. Compruébalo:
   ```bash
   curl "http://localhost:8080/fdsnws/event/1/query?format=geojson&starttime=2026-10-19T00:00:00"
   ```
   Responde un GeoJSON con el mismo formato de propiedades que EMSC (`unid`, `time`, `lat`, `lon`,
   `depth`, `mag`, `magtype="gqm"`, `flynn_region`), o **204** si no hay sismos. Incluye los sismos
   en curso y los archivados.
3. Conéctalo:
   - **Backend sismo-rt:** `GLOBALQUAKE_URL=http://localhost:8080` en `.env`. Se consulta cada 5 s
     (`GLOBALQUAKE_INTERVALO_S`).
   - **Skill de Claude `sismos`:** `SISMOS_GQ_URL=http://localhost:8080` (o `--gq-url`).

Limitaciones verificadas en el código: no implementa búsqueda por radio (`lat/lon/maxradius`), `limit`
ni `orderby`. Por eso se piden los sismos recientes y el filtro por distancia se hace aquí. Es una API
de consulta (polling) y no push, pero al ser local se puede consultar cada pocos segundos sin problema.

## Opción B: hook en un fork (push inmediato)

Si quieres cero latencia de polling, puedes modificar GlobalQuake (MIT) para que haga un `POST` a
`/api/ingest` de sismo-rt al crear o actualizar un sismo. Nombres verificados en la rama `0.11.0`:

- `globalquake.core.events.GlobalQuakeEventListener`: **clase** (no interfaz) con métodos vacíos
  `onQuakeCreate(QuakeCreateEvent)`, `onQuakeUpdate(QuakeUpdateEvent)`, `onQuakeRemove`, etc.
- `QuakeCreateEvent` / `QuakeUpdateEvent` son `record`s con el campo `earthquake()`.
- Registro: `GlobalQuake.instance.getEventHandler().registerEventListener(...)` (en el servidor:
  `GlobalQuakeServer.instance.getEventHandler()`). Los eventos se entregan en un hilo propio.
- `globalquake.core.earthquake.data.Earthquake`: `getUuid()`, `getOrigin()` (epoch ms), `getLat()`,
  `getLon()`, `getDepth()` (km), `getMag()`, `getRegion()`.

```java
GlobalQuake.instance.getEventHandler().registerEventListener(new GlobalQuakeEventListener() {
    @Override public void onQuakeCreate(QuakeCreateEvent e) { SismoRtHook.enviar(e.earthquake()); }
    @Override public void onQuakeUpdate(QuakeUpdateEvent e) { SismoRtHook.enviar(e.earthquake()); }
});
```

```java
import globalquake.core.earthquake.data.Earthquake;
import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.Locale;

public final class SismoRtHook {
    private static final HttpClient HTTP = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3)).build();
    private static final String URL = System.getenv().getOrDefault("SISMO_RT_URL", "http://localhost:8000/api/ingest");
    private static final String TOKEN = System.getenv("SISMO_RT_TOKEN");

    public static void enviar(Earthquake q) {
        if (TOKEN == null || q.getOrigin() == 0L) return;
        String region = q.getRegion() == null ? "" : q.getRegion().replace("\\", "").replace("\"", "'");
        String json = String.format(Locale.ROOT,
            "{\"id\":\"%s\",\"tiempo\":%d,\"lat\":%.4f,\"lon\":%.4f,\"prof_km\":%.1f,\"mag\":%.2f,\"lugar\":\"%s\"}",
            q.getUuid(), q.getOrigin(), q.getLat(), q.getLon(), q.getDepth(), q.getMag(), region);
        HttpRequest req = HttpRequest.newBuilder(URI.create(URL))
            .timeout(Duration.ofSeconds(3))
            .header("Content-Type", "application/json")
            .header("Authorization", "Bearer " + TOKEN)
            .POST(HttpRequest.BodyPublishers.ofString(json)).build();
        // Asíncrono: nunca bloquear el hilo de eventos de GlobalQuake.
        HTTP.sendAsync(req, HttpResponse.BodyHandlers.discarding());
    }
}
```

Este código no se compiló contra GlobalQuake en este repositorio: los nombres se verificaron leyendo
el código fuente de la rama `0.11.0`.

### Contrato de `/api/ingest`

```text
POST /api/ingest
Authorization: Bearer <INGEST_TOKEN>
Content-Type: application/json

{"id": "<uuid>", "tiempo": 1792411200500, "lat": -27.45, "lon": -70.75, "prof_km": 35.0, "mag": 5.3,
 "lugar": "Atacama, Chile"}
```

`tiempo` acepta epoch en ms o ISO 8601 UTC. Reenvía el mismo `id` en cada revisión: el backend
actualiza el evento y solo vuelve a notificar si el nivel sube. Respuesta: `202`.

Prueba sin GlobalQuake:

```bash
curl -X POST http://localhost:8000/api/ingest \
  -H "Authorization: Bearer $INGEST_TOKEN" -H "Content-Type: application/json" \
  -d '{"id":"prueba-1","tiempo":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'","lat":-27.6,"lon":-70.9,"prof_km":30,"mag":5.8}'
```
