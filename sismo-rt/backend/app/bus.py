"""Bus de eventos: fusiona reportes de varias fuentes y los reparte a los clientes conectados.

Todo ocurre en el mismo event loop de asyncio. La difusión es síncrona y solo hace
cálculos baratos + `put_nowait` en la cola de cada cliente, así que un sismo nuevo
llega a todos los sockets sin esperar a ninguna E/S (las notificaciones lentas, como
ntfy, consumen su propia cola en otra tarea).
"""

from __future__ import annotations

import asyncio
import itertools
import logging
from datetime import timedelta

from . import sismologia as sis
from .config import Config
from .modelos import Evento, Filtro, Reporte, ahora, evaluar

log = logging.getLogger("sismo.bus")

# Dos reportes de fuentes distintas son el mismo sismo si coinciden en tiempo y lugar.
MAX_DT_S = 90
MAX_DIST_KM = 150

_contador = itertools.count(1)


class Suscriptor:
    """Un cliente conectado (WebSocket, SSE o notificador interno) con su propio filtro."""

    def __init__(self, cfg: Config, filtro: Filtro | None = None, nombre: str = "", max_cola: int = 200):
        self.cfg = cfg
        self.filtro = filtro
        self.nombre = nombre or f"cliente-{next(_contador)}"
        self.cola: asyncio.Queue[dict] = asyncio.Queue(maxsize=max_cola)
        self._niveles: dict[str, str | None] = {}  # último nivel notificado por evento

    def mensaje(self, evento: Evento, accion: str) -> dict | None:
        datos = evento.a_dict()
        if self.filtro is None:
            return {"tipo": "sismo", "accion": accion, "evento": datos, "usuario": None, "notificar": False}
        if datos["mag"] < self.filtro.mag_min:
            return None
        usuario = evaluar(evento, self.filtro, self.cfg)
        previo = self._niveles.get(evento.id)
        nivel = usuario["nivel"]
        escala = _rango(nivel) > _rango(previo)
        # Se notifica la primera vez que el evento es relevante y cada vez que sube de nivel
        # (p. ej. la magnitud se corrige al alza), nunca por correcciones menores.
        notificar = bool(nivel) and usuario["reciente"] and escala
        if escala:
            self._niveles[evento.id] = nivel
        return {"tipo": "sismo", "accion": accion, "evento": datos, "usuario": usuario, "notificar": notificar}

    def enviar(self, mensaje: dict) -> None:
        try:
            self.cola.put_nowait(mensaje)
        except asyncio.QueueFull:  # cliente lento: se descarta lo más viejo, nunca se bloquea el bus
            try:
                self.cola.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self.cola.put_nowait(mensaje)
            log.warning("Cola llena para %s, se descartó un mensaje antiguo", self.nombre)

    def entregar(self, evento: Evento, accion: str) -> None:
        msg = self.mensaje(evento, accion)
        if msg is not None:
            self.enviar(msg)


def _rango(nivel: str | None) -> int:
    return {None: 0, "info": 1, "alerta": 2}[nivel]


class Bus:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.eventos: dict[str, Evento] = {}
        self._indice: dict[tuple[str, str], str] = {}  # (fuente, id_fuente) -> id de evento
        self.suscriptores: set[Suscriptor] = set()
        self.estado_fuentes: dict[str, dict] = {}

    # --- suscripciones -------------------------------------------------------

    def suscribir(self, s: Suscriptor) -> None:
        self.suscriptores.add(s)

    def desuscribir(self, s: Suscriptor) -> None:
        self.suscriptores.discard(s)

    def snapshot(self, s: Suscriptor) -> dict:
        """Eventos recientes evaluados para un cliente (para pintar el mapa al conectar).

        No marca nada para notificar: el snapshot es historia, no una alerta.
        """
        eventos = []
        for ev in self.recientes():
            msg = s.mensaje(ev, "snapshot")
            if msg is not None:
                eventos.append({"evento": msg["evento"], "usuario": msg["usuario"]})
                if msg["usuario"] and msg["usuario"]["nivel"]:
                    s._niveles[ev.id] = msg["usuario"]["nivel"]
        return {"tipo": "snapshot", "eventos": eventos, "fuentes": self.estado_fuentes}

    # --- estado de fuentes ---------------------------------------------------

    def actualizar_fuente(self, nombre: str, **estado) -> None:
        actual = self.estado_fuentes.setdefault(nombre, {"estado": "iniciando", "eventos": 0, "errores": 0})
        cambio_estado = "estado" in estado and estado["estado"] != actual.get("estado")
        actual.update(estado)
        actual["actualizado"] = ahora().isoformat(timespec="seconds")
        if cambio_estado:
            log.info("Fuente %s -> %s", nombre, actual["estado"])
            msg = {"tipo": "fuentes", "fuentes": self.estado_fuentes}
            for s in list(self.suscriptores):
                s.enviar(msg)

    # --- ingreso de reportes -------------------------------------------------

    def recibir(self, rep: Reporte) -> Evento | None:
        """Incorpora un reporte. Devuelve el evento si fue nuevo o cambió de forma significativa."""
        evento = self._buscar(rep)
        if evento is None:
            evento = Evento(id=f"{rep.fuente}:{rep.id_fuente}", reportes={rep.fuente: rep})
            self.eventos[evento.id] = evento
            self._indice[(rep.fuente, rep.id_fuente)] = evento.id
            self._purgar()
            self._difundir(evento, "nuevo")
            return evento

        antes = evento.principal
        nueva_fuente = rep.fuente not in evento.reportes
        evento.reportes[rep.fuente] = rep
        self._indice[(rep.fuente, rep.id_fuente)] = evento.id
        if nueva_fuente or _cambio_significativo(antes, evento.principal):
            evento.version += 1
            self._difundir(evento, "actualizacion")
            return evento
        return None

    def _buscar(self, rep: Reporte) -> Evento | None:
        id_ev = self._indice.get((rep.fuente, rep.id_fuente))
        if id_ev and id_ev in self.eventos:
            return self.eventos[id_ev]
        mejor, mejor_dist = None, MAX_DIST_KM
        for ev in self.eventos.values():
            if rep.fuente in ev.reportes:  # una fuente no reporta dos veces el mismo sismo con IDs distintos
                continue
            p = ev.principal
            if abs((p.tiempo - rep.tiempo).total_seconds()) > MAX_DT_S:
                continue
            d = sis.distancia_km(p.lat, p.lon, rep.lat, rep.lon)
            if d <= mejor_dist:
                mejor, mejor_dist = ev, d
        return mejor

    def _difundir(self, evento: Evento, accion: str) -> None:
        for s in list(self.suscriptores):
            try:
                s.entregar(evento, accion)
            except Exception:  # un cliente defectuoso no debe frenar al resto
                log.exception("Error entregando a %s", s.nombre)

    def recientes(self) -> list[Evento]:
        return sorted(self.eventos.values(), key=lambda e: e.principal.tiempo, reverse=True)

    def _purgar(self) -> None:
        limite = ahora() - timedelta(hours=self.cfg.retencion_h)
        viejos = [e for e in self.eventos.values() if e.principal.tiempo < limite]
        sobrantes = len(self.eventos) - len(viejos) - self.cfg.max_eventos
        if sobrantes > 0:
            vigentes = sorted((e for e in self.eventos.values() if e.principal.tiempo >= limite),
                              key=lambda e: e.principal.tiempo)
            viejos.extend(vigentes[:sobrantes])
        for ev in viejos:
            self.eventos.pop(ev.id, None)
            for r in ev.reportes.values():
                self._indice.pop((r.fuente, r.id_fuente), None)


def _cambio_significativo(a: Reporte, b: Reporte) -> bool:
    return (
        a.fuente != b.fuente
        or abs(a.mag - b.mag) >= 0.1
        or sis.distancia_km(a.lat, a.lon, b.lat, b.lon) >= 5
        or abs((a.prof_km or 0) - (b.prof_km or 0)) >= 5
    )
