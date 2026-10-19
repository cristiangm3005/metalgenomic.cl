"""Push al celular vía ntfy.sh para una ubicación fija (funciona aunque el navegador esté cerrado)."""

from __future__ import annotations

import asyncio
import base64
import logging

import httpx

from .bus import Bus, Suscriptor
from .config import Config
from .modelos import Filtro

log = logging.getLogger("sismo.ntfy")


def _cabecera_utf8(texto: str) -> str:
    # Las cabeceras HTTP son latin-1; ntfy acepta codificación RFC 2047 para UTF-8.
    return "=?UTF-8?B?" + base64.b64encode(texto.encode()).decode() + "?="


def formatear(msg: dict, lugar: str) -> tuple[str, str, str]:
    ev, u = msg["evento"], msg["usuario"]
    alerta = u["nivel"] == "alerta"
    titulo = (f"{'⚠️ ALERTA SÍSMICA' if alerta else 'Sismo'} M{ev['mag']:.1f} "
              f"a {u['distancia_km']:.0f} km de {lugar}")
    lineas = [
        f"{ev['lugar']}".strip(),
        f"Intensidad estimada en {lugar}: {u['mmi_romano']} ({u['mmi_descripcion']}), PGA ~{u['pga_g'] * 100:.1f}% g",
        f"{u['distancia_km']:.0f} km al {u['rumbo']} · profundidad {ev['prof_km'] if ev['prof_km'] is not None else '?'} km",
        f"Fuentes: {', '.join(ev['fuentes'])}{'' if ev['confirmado'] else ' (sin confirmar)'}",
    ]
    if u["s_restante_s"] > 0:
        lineas.insert(0, f"Onda S llega en ~{u['s_restante_s']:.0f} s")
    if ev["url"]:
        lineas.append(ev["url"])
    prioridad = "urgent" if alerta and u["mmi"] >= 5 else "high" if alerta else "default"
    return titulo, "\n".join(l for l in lineas if l), prioridad


class NotificadorNtfy:
    def __init__(self, cfg: Config, bus: Bus):
        self.cfg = cfg
        self.bus = bus
        filtro = Filtro.por_defecto(cfg, cfg.casa_lat, cfg.casa_lon)
        self.suscriptor = Suscriptor(cfg, filtro, nombre=f"ntfy:{cfg.casa_nombre}")

    @classmethod
    def desde_config(cls, cfg: Config, bus: Bus) -> "NotificadorNtfy | None":
        if cfg.ntfy_topic and cfg.casa_lat is not None and cfg.casa_lon is not None:
            return cls(cfg, bus)
        return None

    async def correr(self) -> None:
        self.bus.suscribir(self.suscriptor)
        headers = {"Tags": "warning,earth_americas"}
        if self.cfg.ntfy_token:
            headers["Authorization"] = f"Bearer {self.cfg.ntfy_token}"
        async with httpx.AsyncClient(timeout=15, headers=headers) as cliente:
            try:
                while True:
                    msg = await self.suscriptor.cola.get()
                    if msg.get("tipo") != "sismo" or not msg.get("notificar"):
                        continue
                    titulo, cuerpo, prioridad = formatear(msg, self.cfg.casa_nombre)
                    try:
                        r = await cliente.post(
                            f"{self.cfg.ntfy_server}/{self.cfg.ntfy_topic}",
                            content=cuerpo.encode(),
                            headers={"Title": _cabecera_utf8(titulo), "Priority": prioridad},
                        )
                        r.raise_for_status()
                        log.info("ntfy enviado: %s", titulo)
                    except httpx.HTTPError as exc:
                        log.warning("No se pudo enviar a ntfy: %s", exc)
            finally:
                self.bus.desuscribir(self.suscriptor)
