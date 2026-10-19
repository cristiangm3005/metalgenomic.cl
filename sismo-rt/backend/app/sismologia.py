"""Cálculos geodésicos y sismológicos: distancia, intensidad (MMI), PGA y llegada de ondas.

Todas las estimaciones son aproximadas y sirven para orientar al usuario, no para
tomar decisiones de ingeniería.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

RADIO_TIERRA_KM = 6371.0088
ROMANOS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
DESCRIPCION_MMI = {
    1: "No sentido",
    2: "Muy débil",
    3: "Débil",
    4: "Ligero",
    5: "Moderado",
    6: "Fuerte",
    7: "Muy fuerte",
    8: "Severo",
    9: "Violento",
    10: "Extremo",
}


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia de gran círculo (fórmula de Haversine) en km."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RADIO_TIERRA_KM * math.asin(min(1.0, math.sqrt(a)))


def rumbo(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """Dirección cardinal aproximada desde el punto 1 hacia el punto 2."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    grados = (math.degrees(math.atan2(x, y)) + 360) % 360
    return ["N", "NE", "E", "SE", "S", "SO", "O", "NO"][int((grados + 22.5) // 45) % 8]


def distancia_hipocentral_km(epicentral_km: float, prof_km: float | None) -> float:
    return math.hypot(epicentral_km, max(prof_km or 0.0, 0.0))


def mmi_allen2012(mag: float, r_hipo_km: float) -> float:
    """Intensidad de Mercalli Modificada estimada en el sitio.

    Ecuación de predicción de intensidad de Allen, Wald & Worden (2012),
    "Intensity attenuation for active crustal regions", J. Seismol. 16:409-433,
    versión con distancia hipocentral. Devuelve un valor continuo acotado a [1, 10].
    """
    c0, c1, c2, c3, c4 = 2.085, 1.428, -1.402, 0.078, -0.209
    r = math.sqrt(r_hipo_km**2 + (1 + c3 * math.exp(mag - 5)) ** 2)
    mmi = c0 + c1 * mag + c2 * math.log(r)
    if r_hipo_km > 50:
        mmi += c4 * math.log(r_hipo_km / 50)
    return min(10.0, max(1.0, mmi))


def pga_desde_mmi(mmi: float) -> float:
    """PGA aproximada (en g) invirtiendo la relación MMI-PGA de Worden et al. (2012), BSSA 102(1)."""
    if mmi <= 1.78 + 1.55 * 1.57:  # tramo de baja intensidad (log10 PGA <= 1.57)
        log_pga = (mmi - 1.78) / 1.55
    else:
        log_pga = (mmi + 1.60) / 3.70
    return (10**log_pga) / 980.665  # cm/s² -> g


def mmi_entero(mmi: float) -> int:
    return int(min(10, max(1, round(mmi))))


def romano(mmi: float) -> str:
    return ROMANOS[mmi_entero(mmi) - 1]


def tiempos_llegada(
    origen: datetime, r_hipo_km: float, vp_km_s: float, vs_km_s: float
) -> tuple[datetime, datetime]:
    """Hora estimada de llegada de las ondas P y S con velocidades medias constantes.

    Es una aproximación de trayectoria recta: razonable hasta unos cientos de km,
    subestima los tiempos a distancias telesísmicas.
    """
    return (
        origen + timedelta(seconds=r_hipo_km / vp_km_s),
        origen + timedelta(seconds=r_hipo_km / vs_km_s),
    )
