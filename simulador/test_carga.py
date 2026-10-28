"""Pruebas del simulador. Ejecutar con:  python3 test_carga.py

Las primeras pruebas repiten, caso por caso, las de web/model.test.js, que a su
vez reproducen la calculadora institucional observada el 10-10-2026. Así el
crédito PUCV en Python queda anclado a la calculadora oficial.
"""

import math

import carga as C


def cerca(a, b, tol=1e-9):
    assert abs(a - b) <= tol, f"{a} != {b}"


# --- Paridad con la calculadora institucional -----------------------------
cerca(C.credito_asignatura({"bloques": 3, "alumnos": 40, "profesores": 1}), 2.45)
cerca(C.credito_asignatura({"bloques": 3, "alumnos": 40, "profesores": 2}), 1.225)

cerca(C.credito_pucv({"docencia": {"tesistas": 4, "talleres": 2, "diplomado": True}})["docencia"], 4 * 35 / 60 + 2 + 2)
assert C.credito_pucv({"investigacion": {"articulos": 9}})["investigacion"] == 16
assert C.credito_pucv({"investigacion": {"proyectosExternosResponsable": 1, "articulos": 4}})["investigacion"] == 15
assert C.credito_pucv({"gestion": {"cargos": ["jefeDocenciaConApoyo", "jefeDocenciaSinApoyo"]}})["gestion"] == 20

mixto = C.credito_pucv({
    "docencia": {"asignaturas": [{"bloques": 4, "alumnos": 25, "profesores": 1}], "tesistas": 2},
    "investigacion": {"proyectosCoinvestigador": 1},
    "vinculacion": {"asistenciaTecnica": True},
    "gestion": {"cargos": ["jefeInvestigacion"]},
})
cerca(mixto["total"], (4 * 35 * 1.25 / 60) + (2 * 35 / 60) + 5 + 2 + 3)

web = C.credito_pucv({
    "docencia": {"asignaturas": [{"bloques": 3, "alumnos": 40, "profesores": 1}], "tesistas": 4, "talleres": 2, "diplomado": True},
    "investigacion": {"proyectosExternosResponsable": 1, "proyectosCoinvestigador": 2, "articulos": 4, "proyectosNoAdjudicados": 1},
    "vinculacion": {k: True for k in C.PESOS_VINCULACION},
    "gestion": {"cargos": ["decano", "jefeInvestigacion"]},
})
cerca(web["docencia"], 8.783333333333333)
cerca(web["investigacion"], 27)
cerca(web["vinculacion"], 12.5)
cerca(web["gestion"], 23)
assert f"{web['total']:.2f}" == "71.28"

# El desglose por nivel de tesistas debe acreditar lo mismo que el total.
cerca(C.credito_pucv({"docencia": {"tesistas": {"pregrado": 1, "magister": 2, "doctorado": 1}}})["docencia"], 4 * 35 / 60)
# Vinculación: la calculadora reconoce una sola actividad por categoría.
assert C.credito_pucv({"vinculacion": {"lineasVinculacion": 3}})["vinculacion"] == 1

# --- Horas reales -----------------------------------------------------------
P = C.cargar_parametros()
Rc = C.resolver(P, "central")

# Asignatura de pregrado, 4 bloques y 40 estudiantes, valores centrales:
# contacto 2,333 h × (1 + 1,5) + (1,5×40 + 12 + 0,5×40)/17 = 5,833 + 5,412.
ug = {"bloques": 4, "alumnos": 40, "nivel": "pregrado", "tipo": "estandar"}
cerca(C.horas_asignatura(ug, Rc), 4 * 35 / 60 * 2.5 + (60 + 12 + 20) / 17)
# En modo anual se promedia sobre 44 semanas con 34 lectivas.
cerca(C.horas_asignatura(ug, Rc, "anual"), C.horas_asignatura(ug, Rc) * 34 / 44)
# Docencia compartida: horas reales divididas igual que el crédito.
cerca(C.horas_asignatura({**ug, "profesores": 2}, Rc), C.horas_asignatura(ug, Rc) / 2)

# Neutralidad: en vinculación, una actividad por categoría cuesta lo acreditado.
uno = {"vinculacion": {"lineasVinculacion": 1, "politicasPublicas": 1}}
cerca(C.horas_reales(uno, Rc)["vinculacion"], C.credito_pucv(uno)["vinculacion"])

# Los niveles son monótonos en el perfil mínimo.
perf = {p["id"]: p["datos"] for p in C.cargar_perfiles()}
tot = [C.horas_reales(perf["minimo"], C.resolver(P, n))["total"] for n in C.NIVELES]
assert tot[0] < tot[1] < tot[2], tot

# El perfil mínimo cumple exactamente los cuatro mínimos.
assert all(C.credito_pucv(perf["minimo"])["cumple"].values())

# Costo de los mínimos: proporcionalidad.
cr = C.credito_pucv(perf["minimo"])
re = C.horas_reales(perf["minimo"], Rc)
cm = C.costo_minimos(cr, re)
cerca(cm["docencia"], re["docencia"] * 8 / cr["docencia"])
assert math.isnan(C.costo_minimos(C.credito_pucv({}), C.horas_reales({}, Rc))["docencia"])

# Monte Carlo reproducible con semilla fija.
a = C.monte_carlo(perf["minimo"], P, n=300)
b = C.monte_carlo(perf["minimo"], P, n=300)
assert a == b

# La media analítica coincide con la media de Monte Carlo (linealidad del modelo).
M_ = C.muestras(P, 4000, semilla=7)
for pid in perf:
    mc_ = sum(C.horas_reales(perf[pid], R)["total"] for R in M_) / len(M_)
    an_ = C.horas_reales(perf[pid], C.resolver(P, "media"))["total"]
    assert abs(mc_ - an_) < 0.25, (pid, mc_, an_)
# Los artículos en revistas de baja exigencia valen 4 h en la calculadora oficial.
assert C.credito_pucv({"investigacion": {"articulosBajaExigencia": 2}})["investigacion"] == 8

print("OK: simulador verificado")
