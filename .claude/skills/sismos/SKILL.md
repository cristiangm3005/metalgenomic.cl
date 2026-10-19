---
name: sismos
description: Vigila sismos y temblores cerca de la ubicación del usuario (por defecto Copiapó, Chile) usando USGS, EMSC y, si está configurado, el backend sismo-rt con GlobalQuake, y avisa en la conversación apenas se detecta uno. Úsala cuando el usuario diga "avísame si tiembla", "vigila los sismos", "¿hubo temblores cerca?", "¿tembló?", "último sismo", "GlobalQuake", "alerta sísmica" o pregunte por terremotos recientes o en curso.
---

# Vigilancia de sismos

El script `scripts/sismos.py` (solo Python estándar, 3.9+) consulta las fuentes sísmicas y calcula
para la ubicación del usuario la distancia, la dirección y la **intensidad estimada (Mercalli)**.

## Antes de responder: qué NO puede hacer

Ningún sistema puede **predecir** terremotos, ni siquiera GlobalQuake. Lo que sí hace esta skill es avisar
lo antes posible cuando un sismo **ya fue detectado**. Si el usuario pide "avísame cuando va a temblar",
díselo en una frase y ofrece la vigilancia. Con USGS y EMSC el aviso llega entre 1 y 20 minutos después
del sismo. Solo con GlobalQuake (vía sismo-rt) puede llegar en segundos. Para emergencias, la fuente
oficial en Chile es el SAE de SENAPRED y el CSN (sismologia.cl).

## Ubicación y umbrales

Por defecto: Copiapó (-27.3668, -70.3314), radio 500 km, M≥6.0 en todo el mundo, ignora M<3.0.
Si el usuario menciona otra ciudad o coordenadas, pásalas con `--lat --lon --lugar` (usa coordenadas
que conozcas de la ciudad). También se pueden fijar con las variables `SISMOS_LAT`, `SISMOS_LON`,
`SISMOS_LUGAR`, `SISMOS_RADIO_KM`, `SISMOS_MAG_GLOBAL`, `SISMOS_MAG_MIN`.

La ruta del script es relativa a esta skill: `.claude/skills/sismos/scripts/sismos.py`.

## Pregunta puntual: "¿hubo temblores?"

```bash
python3 .claude/skills/sismos/scripts/sismos.py ahora --horas 24
```

Usa `--json` si necesitas procesar los datos. Resume para el usuario: los sismos más relevantes
(los de mayor intensidad estimada primero), con magnitud, distancia, dirección, hora de Chile e
intensidad. Si no hubo ninguno, dilo. Si el script escribe `ERROR fuente ...`, avisa que esa fuente
falló. Con código de salida 2 fallaron las dos fuentes: no digas "no hubo sismos".

## Vigilancia continua: "avísame si tiembla"

1. Arranca el monitor con el tool **Monitor** (no con Bash):
   - `command`: `python3 -u .claude/skills/sismos/scripts/sismos.py vigilar` (más `--lat/--lon/--lugar`
     si corresponde)
   - `description`: `sismos cerca de <lugar>`
   - `timeout_ms`: `1800000` (máximo)
2. Confirma al usuario en una línea qué vigilas (lugar, radio, magnitud) y que el aviso llega con el
   retraso de las fuentes.
3. Cada línea del monitor es un evento:
   - `VIGILANDO ...` → arranque correcto, no hace falta decir nada más.
   - `SISMO nivel=ALERTA ...` → **avisa de inmediato** al usuario, primero lo esencial: magnitud,
     distancia, intensidad estimada y hora. Si la intensidad es V o mayor, añade en 2-3 líneas las
     medidas de autoprotección (agacharse, cubrirse y afirmarse; alejarse de ventanas; si estás en
     la costa y el movimiento fue fuerte o largo, evacuar a zona alta sin esperar la alerta oficial)
     y que revise SENAPRED y el SHOA.
   - `SISMO nivel=INFO ...` → avísale de forma breve (sismo lejano o débil en su ubicación).
   - Si la línea dice `(actualización)` → se corrigió la magnitud o subió el nivel. Avisa el cambio.
   - Si la línea incluye `SIN_CONFIRMAR` → detección preliminar (GlobalQuake). Dilo así.
   - `ESTADO fuente=X CAIDA` → avisa que esa fuente no responde y que la vigilancia puede no ver sismos.
     Con `RECUPERADA`, avisa en una línea que volvió.
4. El monitor expira a los 30 minutos: cuando llegue el aviso de expiración, **vuelve a armarlo** con el
   mismo comando sin preguntar, salvo que el usuario haya pedido parar. El script recuerda lo ya
   avisado (`~/.cache/claude-skill-sismos/estado.json`), así que al rearmar no repite sismos.
5. Si el usuario pide parar, detén el monitor con TaskStop.

Para probar que el aviso funciona sin esperar un sismo real:
`python3 .claude/skills/sismos/scripts/sismos.py prueba` imprime un sismo ficticio con el mismo formato.

## GlobalQuake (tiempo real)

GlobalQuake no publica una API. Para usar sus detecciones:

1. Corre el backend `sismo-rt/` de este repo (`uvicorn app.main:app`). Ya recibe en tiempo real el
   WebSocket de EMSC.
2. Conecta GlobalQuake con el hook de `sismo-rt/docs/GLOBALQUAKE.md`. Es un fork que hace POST a
   `/api/ingest`.
3. Exporta `SISMOS_RT_URL=http://localhost:8000` (o pasa `--rt-url`). El vigilante escucha el flujo SSE
   de sismo-rt y, si se cae, vuelve solo a consultar USGS/EMSC.

## Red necesaria

Hosts: `earthquake.usgs.gov` y `www.seismicportal.eu` (y el de sismo-rt si se usa). Si ambos fallan
con 403 o un error de túnel en una sesión en la nube, la política de red del entorno los está
bloqueando. Díselo al usuario y que los permita en la configuración del entorno, o que use la skill
desde Claude Code en su computador.
