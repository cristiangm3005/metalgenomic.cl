# Alerta de sismos 🌎

Script en Python que revisa cada minuto los catálogos sísmicos públicos de
**USGS** y **EMSC**, calcula la distancia a tu ubicación (por defecto **Copiapó**)
y te avisa por **Telegram** y/o **ntfy** (notificación push al celular) cuando un
sismo cumple tus reglas de distancia y magnitud.

- Sin dependencias: solo Python 3.9+ (biblioteca estándar).
- Reglas escalonadas: por ejemplo M3.5+ cerca, M7+ lejos (posible tsunami).
- No repite alertas: un mismo sismo informado por USGS y EMSC se avisa una sola vez,
  aunque reinicies el programa. Si la magnitud se revisa +0.5 o más al alza, envía una
  actualización.
- Mensaje con magnitud, hora de Chile, distancia y dirección (p. ej. "44 km al O de
  Copiapó"), profundidad y enlace al evento.

> ⚠️ **No es un sistema de alerta temprana.** Los catálogos publican los sismos con
> varios minutos de retraso. Para emergencias, la fuente oficial es el **SAE de
> SENAPRED** (llega solo al celular) y el **Centro Sismológico Nacional**
> ([sismologia.cl](https://www.sismologia.cl)). Úsalo como complemento informativo.

## Puesta en marcha

```bash
cd alerta-sismos
cp .env.example .env      # edita tu ubicación, reglas y canales de aviso
python3 alerta_sismos.py --prueba   # envía una notificación de prueba
python3 alerta_sismos.py --listar   # muestra los sismos de la última hora y su distancia
python3 alerta_sismos.py            # queda vigilando (Ctrl+C para salir)
```

Sin Telegram ni ntfy configurados, las alertas solo se muestran en la consola.

### Avisos al celular con ntfy (lo más fácil)

1. Instala la app **ntfy** (Android / iOS).
2. Suscríbete a un tema con un nombre difícil de adivinar, p. ej. `sismos-copiapo-x7k2q9`.
3. Pon ese nombre en `NTFY_TOPIC` del `.env`.

Los sismos fuertes o cercanos se envían con prioridad `high` / `urgent`, que en el
celular suenan aunque esté en modo "no molestar" si así lo configuras en la app.

### Avisos por Telegram

1. Habla con [@BotFather](https://t.me/BotFather), crea un bot y copia el token en `TELEGRAM_TOKEN`.
2. Escríbele cualquier mensaje a tu bot.
3. Abre `https://api.telegram.org/bot<TOKEN>/getUpdates` y copia el `chat.id` en `TELEGRAM_CHAT_ID`.

## Configuración (`.env`)

| Variable | Por defecto | Qué hace |
|---|---|---|
| `LAT`, `LON`, `LUGAR` | Copiapó | Tu ubicación y el nombre que aparece en el mensaje |
| `REGLAS` | `100:3.5,300:4.5,800:6.0,2000:7.0` | Pares `radio_km:magnitud_mínima`; avisa si se cumple cualquiera |
| `INTERVALO_S` | `60` | Segundos entre consultas |
| `VENTANA_MIN` | `60` | Minutos hacia atrás que se revisan en cada consulta |
| `FUENTES` | `usgs,emsc` | Catálogos a consultar |
| `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` | — | Canal Telegram |
| `NTFY_TOPIC`, `NTFY_SERVER`, `NTFY_TOKEN` | — | Canal ntfy (el token solo si usas un servidor con autenticación) |
| `ARCHIVO_ESTADO` | `estado.json` | Dónde se recuerdan los sismos ya avisados |

## Dejarlo corriendo siempre

- **Linux / Raspberry Pi:** usa el servicio incluido, `alerta-sismos.service` (las
  instrucciones están dentro del archivo).
- **cron** (alternativa): `* * * * * cd /ruta/alerta-sismos && python3 alerta_sismos.py --once`
- **Windows:** Programador de tareas → ejecutar `python alerta_sismos.py` al iniciar sesión.

## Pruebas

```bash
cd alerta-sismos
python3 -m unittest -v
```

Las pruebas no usan la red.

## Ideas para más adelante

- Sumar el CSN (sismologia.cl) como tercera fuente.
- Escuchar un servidor propio de [GlobalQuake](https://github.com/xspanger3770/GlobalQuake)
  para detecciones más rápidas (es experimental: tómalo solo como referencia).
