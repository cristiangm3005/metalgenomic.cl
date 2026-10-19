---
name: sismos
description: Vigila sismos y temblores cerca de la ubicación del usuario (por defecto Copiapó, Chile) usando USGS, EMSC y, si está configurado, GlobalQuake Server o el backend sismo-rt, y avisa en la conversación (y con notificación push) apenas se detecta uno. Úsala cuando el usuario diga "avísame si tiembla", "vigila los sismos", "¿hubo temblores cerca?", "¿tembló?", "último sismo", "GlobalQuake", "alerta sísmica" o pregunte por terremotos recientes o en curso.
---

# Vigilancia de sismos

El script `scripts/sismos.py` (solo Python estándar, 3.9+) consulta las fuentes sísmicas y calcula
para la ubicación del usuario la distancia, la dirección y la **intensidad estimada (Mercalli)**.

## Antes de responder: qué NO puede hacer

Ningún sistema puede **predecir** terremotos, ni siquiera GlobalQuake. Lo que sí hace esta skill es avisar
lo antes posible cuando un sismo **ya fue detectado**. Si el usuario pide "avísame cuando va a temblar",
díselo en una frase y ofrece la vigilancia. Con USGS y EMSC el aviso llega entre 1 y 20 minutos después
del sismo. Solo con GlobalQuake puede llegar en segundos. Para emergencias, la fuente
oficial en Chile es el SAE de SENAPRED y el CSN (sismologia.cl).

## Ubicación y umbrales

Por defecto: Copiapó (-27.3668, -70.3314), radio 500 km, M≥6.0 en todo el mundo, ignora M<3.0.
Si el usuario menciona otra ciudad o coordenadas, pásalas con `--lat --lon --lugar` (usa coordenadas
que conozcas de la ciudad). También se pueden fijar con las variables `SISMOS_LAT`, `SISMOS_LON`,
`SISMOS_LUGAR`, `SISMOS_RADIO_KM`, `SISMOS_MAG_GLOBAL`, `SISMOS_MAG_MIN`.

En los comandos de abajo, `SKILL_DIR` es el directorio base de esta skill (aparece al cargarla):
`~/.claude/skills/sismos` si está instalada para el usuario, o `.claude/skills/sismos` dentro de un
proyecto. Reemplázalo por la ruta real.

## Pregunta puntual: "¿hubo temblores?"

```bash
python3 SKILL_DIR/scripts/sismos.py ahora --horas 24
```

Usa `--json` si necesitas procesar los datos. Resume para el usuario: los sismos más relevantes
(los de mayor intensidad estimada primero), con magnitud, distancia, dirección, hora de Chile e
intensidad. Si no hubo ninguno, dilo. Si el script escribe `ERROR fuente ...`, avisa que esa fuente
falló. Con código de salida 2 fallaron las dos fuentes: no digas "no hubo sismos".

## Vigilancia continua: "avísame si tiembla"

1. Arranca el monitor con el tool **Monitor** (no con Bash):
   - `command`: `python3 -u SKILL_DIR/scripts/sismos.py vigilar` (más `--lat/--lon/--lugar`
     si corresponde)
   - `description`: `sismos cerca de <lugar>`
   - `timeout_ms`: `1800000` (máximo)
2. Confirma al usuario en una línea qué vigilas (lugar, radio, magnitud) y que el aviso llega con el
   retraso de las fuentes.
3. Cada línea del monitor es un evento:
   - `VIGILANDO ...` → arranque correcto, no hace falta decir nada más.
   - `SISMO nivel=ALERTA ...` → envía primero una notificación con el tool **PushNotification**
     (`status: "proactive"`, una línea de menos de 200 caracteres, p. ej.
     `Sismo M5.4 a 42 km al O de Copiapó, intensidad V. Hora 18:03`). Si el tool no está cargado,
     cárgalo con ToolSearch (`select:PushNotification`). Luego **avisa en el chat** de inmediato, primero lo esencial: magnitud,
     distancia, intensidad estimada y hora. Si la intensidad es V o mayor, añade en 2-3 líneas las
     medidas de autoprotección (agacharse, cubrirse y afirmarse; alejarse de ventanas; si estás en
     la costa y el movimiento fue fuerte o largo, evacuar a zona alta sin esperar la alerta oficial)
     y que revise SENAPRED y el SHOA.
   - `SISMO nivel=INFO ...` → avísale de forma breve en el chat (sismo lejano o débil en su ubicación).
     Envía PushNotification solo si la magnitud es 6.0 o más.
   - Si la línea dice `(actualización)` → se corrigió la magnitud o subió el nivel. Avisa el cambio.
   - Si la línea incluye `SIN_CONFIRMAR` → detección preliminar (GlobalQuake). Dilo así.
   - `ESTADO fuente=X CAIDA` → avisa que esa fuente no responde y que la vigilancia puede no ver sismos.
     Con `RECUPERADA`, avisa en una línea que volvió.
4. El monitor expira a los 30 minutos: cuando llegue el aviso de expiración, **vuelve a armarlo** con el
   mismo comando sin preguntar, salvo que el usuario haya pedido parar. El script recuerda lo ya
   avisado (`~/.cache/claude-skill-sismos/estado.json`), así que al rearmar no repite sismos.
5. Si el usuario pide parar, detén el monitor con TaskStop.

Para probar que el aviso funciona sin esperar un sismo real:
`python3 SKILL_DIR/scripts/sismos.py prueba` imprime un sismo ficticio con el mismo formato.

## GlobalQuake (detección en segundos)

El código abierto de GlobalQuake está descontinuado desde la 1.0.0 (sigue en globalquake.net como
proyecto propietario). **GlobalQuake Server 0.11** trae una API FDSNWS-event, apagada por defecto:

1. En sus settings: `autoStartFDSNWSEventServer=true` (puerto `FDSNWSEventPort`, por defecto 8080).
2. Exporta `SISMOS_GQ_URL=http://localhost:8080` (o pasa `--gq-url`). El vigilante lo consulta cada 5 s
   y además sigue consultando USGS/EMSC. Sus sismos aparecen como `fuentes=globalquake SIN_CONFIRMAR`
   hasta que un catálogo los confirma. GlobalQuake es experimental: dilo al avisar.

Alternativa: el backend `sismo-rt/` de este repo (WebSocket de EMSC en tiempo real + GlobalQuake) con
`SISMOS_RT_URL=http://localhost:8000` (o `--rt-url`). El vigilante escucha su flujo SSE y, si se cae,
vuelve solo a consultar USGS/EMSC. Detalles en `sismo-rt/docs/GLOBALQUAKE.md`.

## Red necesaria

Hosts: `earthquake.usgs.gov` y `www.seismicportal.eu` (y los de GlobalQuake o sismo-rt si se usan). Si ambos fallan
con 403 o un error de túnel en una sesión en la nube, la política de red del entorno los está
bloqueando. Díselo al usuario y que los permita en la configuración del entorno, o que use la skill
desde Claude Code en su computador.
