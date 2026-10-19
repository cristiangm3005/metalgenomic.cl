# Integración con GlobalQuake

[GlobalQuake](https://github.com/xspanger3770/GlobalQuake) (Java, licencia MIT) detecta sismos en
segundos procesando en vivo datos de estaciones (SeedLink). Es la única pieza de este sistema
capaz de avisar **antes** de que lleguen las ondas a ciudades algo alejadas del epicentro.

## Por qué no hay "conector directo"

GlobalQuake no publica una API WebSocket ni REST. Su modo servidor (desde v0.10) usa un
protocolo binario propio entre su servidor y su cliente Java, sin documentación ni garantías
de estabilidad entre versiones. Replicarlo en Python sería frágil.

La integración robusta es un **hook en un fork**: cuando GlobalQuake crea o actualiza un sismo,
envía un `POST` JSON a este backend.

## Contrato del endpoint

```text
POST /api/ingest
Authorization: Bearer <INGEST_TOKEN>
Content-Type: application/json

{
  "id": "a3f1c2",                 // ID estable del sismo en GlobalQuake (el mismo en cada actualización)
  "fuente": "globalquake",        // opcional
  "tiempo": 1792411200500,        // hora de origen: epoch ms o ISO 8601 UTC
  "lat": -27.45, "lon": -70.75,
  "prof_km": 35.0,
  "mag": 5.3,
  "tipo_mag": "gq",               // opcional
  "lugar": "Atacama, Chile"       // opcional
}
```

Respuesta `202 {"aceptado": true, "evento": "<id interno o null si no hubo cambio relevante>"}`.

Reenvía el mismo `id` en cada revisión: el backend actualiza el evento y solo vuelve a notificar
si el nivel sube. Cuando USGS o EMSC publiquen el mismo sismo, se fusiona y pasa a `confirmado: true`.

## Esbozo del hook en Java

GlobalQuake tiene un sistema de eventos internos (creación/actualización de sismos). Los nombres
exactos de clases y métodos varían entre versiones: búscalos en el código de tu versión
(p. ej. `grep -rn "QuakeCreateEvent\|QuakeUpdateEvent" src/`). La idea:

```java
// Registrar junto a los demás listeners al iniciar la aplicación.
GlobalQuake.instance.getEventHandler().registerEventListener(new GlobalQuakeEventListener() {
    @Override public void onQuakeCreate(QuakeCreateEvent e) { SismoRtHook.enviar(e.earthquake()); }
    @Override public void onQuakeUpdate(QuakeUpdateEvent e) { SismoRtHook.enviar(e.earthquake()); }
});
```

```java
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
        if (TOKEN == null) return;
        String json = String.format(Locale.ROOT,
            "{\"id\":\"%s\",\"tiempo\":%d,\"lat\":%.4f,\"lon\":%.4f,\"prof_km\":%.1f,\"mag\":%.2f,\"lugar\":\"%s\"}",
            q.getUuid(), q.getOrigin(), q.getLat(), q.getLon(), q.getDepth(), q.getMag(),
            q.getRegion().replace("\"", "'"));
        HttpRequest req = HttpRequest.newBuilder(URI.create(URL))
            .timeout(Duration.ofSeconds(3))
            .header("Content-Type", "application/json")
            .header("Authorization", "Bearer " + TOKEN)
            .POST(HttpRequest.BodyPublishers.ofString(json)).build();
        // Asíncrono: nunca bloquear el hilo de detección de GlobalQuake.
        HTTP.sendAsync(req, HttpResponse.BodyHandlers.discarding());
    }
}
```

Los getters (`getUuid`, `getOrigin`, `getMag`, ...) son ilustrativos: ajústalos a la clase
`Earthquake` de tu versión.

## Probar sin GlobalQuake

```bash
curl -X POST http://localhost:8000/api/ingest \
  -H "Authorization: Bearer $INGEST_TOKEN" -H "Content-Type: application/json" \
  -d '{"id":"prueba-1","tiempo":"'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'","lat":-27.6,"lon":-70.9,"prof_km":30,"mag":5.8}'
```
