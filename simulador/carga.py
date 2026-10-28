"""Simulador de carga académica PUCV: crédito oficial frente a horas reales.

Dos cálculos sobre el mismo perfil:

* ``credito_pucv`` reproduce exactamente la calculadora institucional del
  Navegador Académico (réplica auditada en ``web/model.js``).
* ``horas_reales`` estima el tiempo efectivamente requerido por cada
  actividad, con parámetros documentados en ``parametros.json`` en tres
  niveles (bajo, central, alto) o muestreados por Monte Carlo.

Todas las cifras son horas por semana. En modo ``"lectiva"`` las asignaturas
se cuentan con su intensidad de semana de clases; en modo ``"anual"`` se
promedian sobre las semanas laborales del año. El crédito PUCV no cambia con
el modo, porque la calculadora institucional no anualiza.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent
NIVELES = ("bajo", "central", "alto")
DIMENSIONES = ("docencia", "investigacion", "vinculacion", "gestion")

# --------------------------------------------------------------------------
# Réplica de la calculadora institucional (web/model.js)
# --------------------------------------------------------------------------

MINIMOS = {"docencia": 8, "investigacion": 2, "vinculacion": 2, "gestion": 2}

PESOS_INVESTIGACION = {
    "proyectosExternosResponsable": 15,
    "proyectosInternosResponsable": 8,
    "proyectosCoinvestigador": 5,
    "articulos": 4,
    "proyectosNoAdjudicados": 2,
    "proyectosInnovacionDocente": 4,
    "otrasInvestigaciones": 1,
}

PESOS_VINCULACION = {
    "lineasVinculacion": 1,
    "asistenciaTecnica": 2,
    "formacionContinua": 3,
    "direccionDivulgacion": 3,
    "presenciaSociedad": 0.5,
    "politicasPublicas": 2,
    "difusionPrePostgrado": 1,
}

CARGOS = {
    "consejeroSuperior": 5, "capitular": 5, "decano": 20, "vicedecano": 10,
    "secretarioFacultad": 15, "directorUnidad": 20, "secretarioAcademico": 10,
    "jefeDocenciaConApoyo": 10, "jefeDocenciaSinApoyo": 20, "jefeExtension": 6,
    "jefeInvestigacion": 3, "directorPostgrado": 6, "jefeCarrera": 6,
    "editorRevista": 6, "comisiones": 2, "directorCentroClinico": 8,
    "tutorPrimerAno": 1, "proyectosInstitucionales": 10, "otraGestion": 1,
}


def _num(valor, entero=False, maximo=float("inf")):
    try:
        n = float(valor)
    except (TypeError, ValueError):
        n = 0.0
    if not np.isfinite(n) or n < 0:
        n = 0.0
    if entero:
        n = float(np.floor(n))
    return min(n, maximo)


def credito_asignatura(a: dict) -> float:
    alumnos = _num(a.get("alumnos"))
    bloques = _num(a.get("bloques", a.get("claves")))
    profesores = max(1.0, _num(a.get("profesores", 1), entero=True))
    return bloques * 35 * (1 + alumnos * 0.01) / (60 * profesores)


def _total_tesistas(tesistas) -> float:
    """La calculadora oficial recibe un solo número; aquí se admite el desglose."""
    if isinstance(tesistas, dict):
        return sum(_num(v) for v in tesistas.values())
    return _num(tesistas)


def _cargos(gestion: dict) -> set:
    sel = set(gestion.get("cargos", []) or [])
    if {"jefeDocenciaConApoyo", "jefeDocenciaSinApoyo"} <= sel:
        sel.discard("jefeDocenciaConApoyo")
    return sel


def credito_pucv(perfil: dict) -> dict:
    doc = perfil.get("docencia", {})
    asign = sum(credito_asignatura(a) for a in doc.get("asignaturas", []))
    guias = _total_tesistas(doc.get("tesistas", 0)) * 35 / 60
    docencia = asign + guias + _num(doc.get("talleres")) + (2 if doc.get("diplomado") else 0)

    inv_in = dict(perfil.get("investigacion", {}))
    # La calculadora oficial no distingue revistas: los artículos de baja exigencia son artículos.
    inv_in["articulos"] = _num(inv_in.get("articulos")) + _num(inv_in.get("articulosBajaExigencia"))
    cant = {k: _num(inv_in.get(k), entero=(k != "articulos"), maximo=(4 if k == "articulos" else float("inf")))
            for k in PESOS_INVESTIGACION}
    bloqueados = cant["proyectosExternosResponsable"] > 0
    if bloqueados:
        cant["articulos"] = 0
    investigacion = sum(cant[k] * p for k, p in PESOS_INVESTIGACION.items())

    vin = perfil.get("vinculacion", {})
    vinculacion = sum(p for k, p in PESOS_VINCULACION.items() if _num(vin.get(k)) > 0 or vin.get(k) is True)

    gestion = sum(CARGOS[k] for k in _cargos(perfil.get("gestion", {})) if k in CARGOS)

    total = docencia + investigacion + vinculacion + gestion
    por_dim = {"docencia": docencia, "investigacion": investigacion,
               "vinculacion": vinculacion, "gestion": gestion}
    return {
        **por_dim,
        "asignaturas": asign,
        "guias": guias,
        "articulosBloqueados": bloqueados,
        "total": total,
        "otras": _num(perfil.get("otrasActividades"), maximo=6),
        "cumple": {d: por_dim[d] >= MINIMOS[d] for d in DIMENSIONES},
    }


# --------------------------------------------------------------------------
# Parámetros
# --------------------------------------------------------------------------

def cargar_parametros(ruta: Path | None = None) -> dict:
    with open(ruta or RAIZ / "parametros.json", encoding="utf-8") as f:
        return json.load(f)


def _es_rango(x) -> bool:
    return isinstance(x, dict) and all(n in x for n in NIVELES)


def resolver(P: dict, nivel: str = "central", rng: np.random.Generator | None = None) -> dict:
    """Reemplaza cada rango {bajo, central, alto} por un número.

    Con ``rng`` se muestrea una distribución triangular con moda en el valor
    central; sin ``rng`` se toma el nivel indicado. El nivel ``"media"`` da la
    media de cada distribución; como las horas reales son lineales en los
    parámetros (y los factores que se multiplican son independientes), evaluar
    el modelo en ese nivel da exactamente la media de las simulaciones.
    """
    def rec(x):
        if _es_rango(x):
            lo, c, hi = (float(x[n]) for n in NIVELES)
            if rng is None:
                if nivel == "media":  # media exacta de la distribución triangular
                    return (lo + c + hi) / 3
                return float(x[nivel])
            a, b = min(lo, hi), max(lo, hi)
            if b - a < 1e-12:
                return c
            return float(rng.triangular(a, min(max(c, a), b), b))
        if isinstance(x, dict):
            return {k: rec(v) for k, v in x.items() if k not in ("fuentes", "nota", "unidad")}
        return x
    return rec(copy.deepcopy(P))


# --------------------------------------------------------------------------
# Horas reales
# --------------------------------------------------------------------------

def horas_asignatura(a: dict, R: dict, modo: str = "lectiva") -> float:
    cal = R["calendario"]
    d = R["docencia"]
    nivel = a.get("nivel", "pregrado")
    tipo = a.get("tipo", "estandar")
    prep = d["preparacion_por_hora_contacto"][nivel if tipo == "estandar" else tipo]
    n = _num(a.get("alumnos"))
    contacto = _num(a.get("bloques", a.get("claves"))) * cal["minutos_bloque"] / 60
    profesores = max(1.0, _num(a.get("profesores", 1), entero=True))
    semestral = (d["evaluacion_por_estudiante_semestre"][nivel] * n
                 + d["coordinacion_semestre"]["base"]
                 + d["coordinacion_semestre"]["por_estudiante"] * n)
    h = (contacto * (1 + prep) + semestral / cal["semanas_lectivas_semestre"]) / profesores
    if modo == "anual":
        h *= cal["semanas_lectivas_anio"] / cal["semanas_laborales_anio"]
    return h


def horas_reales(perfil: dict, R: dict, modo: str = "lectiva") -> dict:
    cal = R["calendario"]
    sem = cal["semanas_laborales_anio"]
    doc_in = perfil.get("docencia", {})

    asign = sum(horas_asignatura(a, R, modo) for a in doc_in.get("asignaturas", []))
    tes = doc_in.get("tesistas", {})
    if not isinstance(tes, dict):  # sin desglose: se supone pregrado
        tes = {"pregrado": tes}
    guias = sum(_num(tes.get(k)) * R["docencia"]["tesis_horas_anio"][k] / sem
                for k in ("pregrado", "magister", "doctorado"))
    talleres = _num(doc_in.get("talleres")) * R["docencia"]["talleres"]
    diplomado = R["docencia"]["diplomado"] if doc_in.get("diplomado") else 0.0
    docencia = asign + guias + talleres + diplomado

    I = R["investigacion"]
    inv = perfil.get("investigacion", {})
    tiene_proyecto = (_num(inv.get("proyectosExternosResponsable")) + _num(inv.get("proyectosInternosResponsable"))) > 0
    libre = 1 - I["fraccion_superpuesta_con_proyecto"] if tiene_proyecto else 1.0
    inv_d = {
        "proyectos": (_num(inv.get("proyectosExternosResponsable")) * I["proyectosExternosResponsable"]
                      + _num(inv.get("proyectosInternosResponsable")) * I["proyectosInternosResponsable"]
                      + _num(inv.get("proyectosCoinvestigador")) * I["proyectosCoinvestigador"]),
        "articulos": libre * (_num(inv.get("articulos")) * I["articulos"]
                              + _num(inv.get("articulosBajaExigencia")) * I["articulosBajaExigencia"]
                              + _num(inv.get("articulosCoautor")) * I["articulosCoautor"]) / sem,
        "propuestas": _num(inv.get("proyectosNoAdjudicados")) * I["proyectosNoAdjudicados"] / sem,
        "otras": (_num(inv.get("proyectosInnovacionDocente")) * I["proyectosInnovacionDocente"]
                  + _num(inv.get("otrasInvestigaciones")) * I["otrasInvestigaciones"]),
        "arbitrajes": _num(inv.get("arbitrajes")) * I["arbitrajes"] / sem,
    }
    if "horasDeclaradasProyecto" in inv:  # dedicación real declarada ante la agencia
        inv_d["proyectos"] = _num(inv["horasDeclaradasProyecto"])
    investigacion = sum(inv_d.values())

    f = R["vinculacion"]["factor_por_actividad"]
    vin = perfil.get("vinculacion", {})
    vinculacion = sum(_num(1 if vin.get(k) is True else vin.get(k)) * p * f for k, p in PESOS_VINCULACION.items())

    gestion = sum(R["gestion"][k] for k in _cargos(perfil.get("gestion", {})) if k in R["gestion"])

    S = R["servicio_no_reconocido"]
    servicio = (S["correo_administracion"] + S["examen_tesis"]) / sem

    otras = _num(perfil.get("otrasActividades"), maximo=6)
    por_dim = {"docencia": docencia, "investigacion": investigacion,
               "vinculacion": vinculacion, "gestion": gestion}
    return {
        **por_dim,
        "asignaturas": asign,
        "guias": guias,
        "investigacion_desglose": inv_d,
        "servicio_no_reconocido": servicio,
        "otras": otras,
        "total": sum(por_dim.values()) + servicio + otras,
    }


# --------------------------------------------------------------------------
# Comparación y costo real de los mínimos
# --------------------------------------------------------------------------

def costo_minimos(cred: dict, real: dict) -> dict:
    """Horas reales que cuesta alcanzar el mínimo de cada dimensión.

    Se atribuye el tiempo real en proporción al crédito: si una dimensión
    acredita C horas con un costo real H, alcanzar el mínimo m cuesta
    H * m / C. Si C es cero, el mínimo no es alcanzable con el perfil dado.
    """
    out = {}
    for d in DIMENSIONES:
        c, h, m = cred[d], real[d], MINIMOS[d]
        out[d] = h * m / c if c > 0 else float("nan")
    out["total"] = sum(out[d] for d in DIMENSIONES)
    out["con_servicio"] = out["total"] + real["servicio_no_reconocido"]
    return out


def comparar(perfil: dict, P: dict, modo: str = "lectiva") -> dict:
    cred = credito_pucv(perfil)
    reales = {n: horas_reales(perfil, resolver(P, n), modo) for n in NIVELES}
    jornada = P["calendario"]["jornada_referencia"]
    minimos_total = sum(MINIMOS.values())
    libres_nominales = jornada - minimos_total
    costos = {n: costo_minimos(cred, reales[n]) for n in NIVELES}
    return {
        "credito": cred,
        "real": reales,
        "costo_minimos": costos,
        "libres_nominales": libres_nominales,
        "libres_efectivas": {n: jornada - costos[n]["con_servicio"] for n in NIVELES},
        "exceso_sobre_jornada": {n: reales[n]["total"] - jornada for n in NIVELES},
    }


def monte_carlo(perfil: dict, P: dict, n: int = 5000, semilla: int = 20261012, modo: str = "lectiva") -> dict:
    rng = np.random.default_rng(semilla)
    cred = credito_pucv(perfil)
    tot, costo = np.empty(n), np.empty(n)
    for i in range(n):
        r = horas_reales(perfil, resolver(P, rng=rng), modo)
        tot[i] = r["total"]
        costo[i] = costo_minimos(cred, r)["con_servicio"]
    pct = lambda x: {"p05": float(np.percentile(x, 5)), "p50": float(np.percentile(x, 50)),
                     "p95": float(np.percentile(x, 95))}
    jornada = P["calendario"]["jornada_referencia"]
    return {
        "total": pct(tot),
        "costo_minimos": pct(costo),
        "prob_total_sobre_jornada": float(np.mean(tot > jornada)),
        "prob_libres_menor_mitad": float(np.mean(jornada - costo < (jornada - sum(MINIMOS.values())) / 2)),
        "credito_total": cred["total"],
    }


def muestras(P: dict, n: int = 5000, semilla: int = 20261012) -> list:
    """Conjuntos de parámetros muestreados (triangular con moda en el valor central)."""
    rng = np.random.default_rng(semilla)
    return [resolver(P, rng=rng) for _ in range(n)]


CLAVES_RESUMEN = DIMENSIONES + ("servicio_no_reconocido", "total")


def resumen(perfil: dict, M: list, P: dict, modo: str = "lectiva") -> dict:
    """Media y percentiles 5 y 95 de las horas reales sobre las muestras M.

    Las medias por dimensión suman la media del total, por eso se usan en las
    barras apiladas. También resume el costo de los mínimos y las horas libres.
    """
    cred = credito_pucv(perfil)
    jornada = P["calendario"]["jornada_referencia"]
    filas = {k: [] for k in CLAVES_RESUMEN}
    costo, libres = [], []
    for R in M:
        r = horas_reales(perfil, R, modo)
        for k in CLAVES_RESUMEN:
            filas[k].append(r[k])
        c = costo_minimos(cred, r)["con_servicio"]
        costo.append(c)
        libres.append(jornada - c)
    est = lambda x: {"media": float(np.mean(x)), "p05": float(np.percentile(x, 5)), "p95": float(np.percentile(x, 95))}
    out = {k: est(v) for k, v in filas.items()}
    out["costo_minimos"] = est(costo)
    out["libres"] = est(libres)
    # Medias exactas (evaluación en el nivel "media"); los percentiles vienen de las muestras.
    rm = horas_reales(perfil, resolver(P, "media"), modo)
    for k in CLAVES_RESUMEN:
        out[k]["media"] = rm[k]
    cm = costo_minimos(cred, rm)["con_servicio"]
    out["costo_minimos"]["media"] = cm
    out["libres"]["media"] = jornada - cm
    out["prob_total_sobre_jornada"] = float(np.mean(np.array(filas["total"]) > jornada))
    out["prob_libres_menor_mitad"] = float(np.mean(np.array(libres) < (jornada - sum(MINIMOS.values())) / 2))
    out["credito"] = cred
    return out


def cargar_perfiles(ruta: Path | None = None) -> list:
    with open(ruta or RAIZ / "perfiles.json", encoding="utf-8") as f:
        return json.load(f)["perfiles"]
