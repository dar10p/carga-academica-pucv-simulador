"""Genera figuras, tablas y cifras del documento a partir del simulador.

Uso:  python3 generar.py

Escribe en ../documento/{figuras,tablas}/, ../documento/numeros.tex y
../web/{parametros.js,perfiles.js,fixtures.json}. Toda cifra que aparece en el
texto proviene de numeros.tex: cambiar un parámetro y volver a ejecutar este
script actualiza el documento completo.

Las horas reales se resumen con la media de N_MC simulaciones de Monte Carlo
(cada parámetro muestreado de una distribución triangular entre sus valores
bajo y alto, con moda en el central) y con el intervalo entre los percentiles
5 y 95, que contiene el 90 % de los resultados.
"""

from __future__ import annotations

import copy
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
import numpy as np  # noqa: E402

import carga as C  # noqa: E402

RAIZ = Path(__file__).resolve().parent
DOC = RAIZ.parent / "documento"
WEB = RAIZ.parent / "web"
FIG = DOC / "figuras"
TAB = DOC / "tablas"
N_MC = 5000
N_CURVAS = 2000  # muestras usadas para curvas y barridos

# ---------------------------------------------------------------- estilo

for ruta in [
    "/usr/share/texmf/fonts/opentype/public/tex-gyre/texgyrepagella-regular.otf",
    "/usr/share/texmf/fonts/opentype/public/tex-gyre/texgyrepagella-bold.otf",
    "/usr/local/texlive/2025/texmf-dist/fonts/opentype/public/tex-gyre/texgyrepagella-regular.otf",
    "/usr/local/texlive/2026/texmf-dist/fonts/opentype/public/tex-gyre/texgyrepagella-regular.otf",
]:
    if Path(ruta).exists():
        font_manager.fontManager.addfont(ruta)

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["TeX Gyre Pagella", "Palatino", "Book Antiqua", "DejaVu Serif"],
    "font.size": 9, "axes.titlesize": 9, "axes.labelsize": 9, "legend.fontsize": 8,
    "xtick.labelsize": 8, "ytick.labelsize": 8,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": "#8a8984", "axes.labelcolor": "#2b2b29",
    "xtick.color": "#52514e", "ytick.color": "#52514e",
    "axes.grid": True, "axes.grid.axis": "y", "grid.color": "#e4e3df", "grid.linewidth": 0.6,
    "axes.axisbelow": True, "pdf.fonttype": 42, "svg.fonttype": "none",
})

# Paleta categórica validada; cada dimensión conserva su color en todas las figuras.
COLOR = {"docencia": "#2a78d6", "investigacion": "#eb6834", "vinculacion": "#1baf7a",
         "gestion": "#eda100", "servicio": "#a3a29c"}
TINTA, TINTA2 = "#1d1d1b", "#52514e"
ETIQUETA = {"docencia": "Docencia", "investigacion": "Investigación", "vinculacion": "Vinculación",
            "gestion": "Gestión", "servicio": "Servicio no reconocido"}
REC = "Horas reconocidas"
REAL = "Horas reales"
ANCHO = 6.1


def guardar(fig, nombre):
    """PDF para LaTeX y SVG para presentaciones o edición."""
    fig.savefig(FIG / f"{nombre}.pdf", bbox_inches="tight")
    fig.savefig(FIG / f"{nombre}.svg", bbox_inches="tight")
    plt.close(fig)


def es(x: float, d: int = 1) -> str:
    """Número con coma decimal y redondeo comercial (igual que el simulador web)."""
    q = Decimal(repr(round(float(x), 9))).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)
    return f"{q:.{d}f}".replace(".", ",")


def pct(x: float) -> str:
    return es(100 * x, 0)


def apilar(ax, x, partes, ancho, etiquetar=True):
    base = 0.0
    for clave, valor in partes:
        if valor <= 0:
            continue
        ax.bar(x, valor, ancho, bottom=base, color=COLOR[clave], edgecolor="white", linewidth=1.0)
        if etiquetar and valor >= 2.2:
            claro = clave in ("docencia", "investigacion")
            ax.text(x, base + valor / 2, es(valor), ha="center", va="center", fontsize=7, color="white" if claro else TINTA)
        base += valor
    return base


def partes_rec(cr):
    return [(d, cr[d]) for d in C.DIMENSIONES]


def partes_real(rs):
    return [(d, rs[d]["media"]) for d in C.DIMENSIONES] + [("servicio", rs["servicio_no_reconocido"]["media"])]


def leyenda(ax, **kw):
    h = [Patch(facecolor=COLOR[k], label=ETIQUETA[k]) for k in COLOR]
    ax.legend(handles=h, frameon=False, **kw)


def bigote(ax, x, rs, clave="total", **kw):
    m = rs[clave]
    ax.errorbar(x, m["media"], yerr=[[m["media"] - m["p05"]], [m["p95"] - m["media"]]],
                color=TINTA, capsize=kw.pop("capsize", 2.5), lw=0.8, fmt="none", **kw)


# ---------------------------------------------------------------- cálculo

P = C.cargar_parametros()
PERFILES = C.cargar_perfiles()
POR_ID = {p["id"]: p for p in PERFILES}
M = C.muestras(P, N_MC)
MC = M[:N_CURVAS]
RES = {p["id"]: C.resumen(p["datos"], M, P) for p in PERFILES}
JORNADA = P["calendario"]["jornada_referencia"]
LIBRES = JORNADA - sum(C.MINIMOS.values())
SEM = P["calendario"]["semanas_laborales_anio"]
FIG.mkdir(parents=True, exist_ok=True)
TAB.mkdir(parents=True, exist_ok=True)


RMEDIA = C.resolver(P, "media")

# ---------------------------------------------------------------- referencia USM (Decreto de Rectoría 258/2015)
# No es un parámetro del simulador: se dibuja solo como referencia externa.
USM = P["referencia_usm"]
USM_COLOR = "#7a5195"


def usm_docencia(d):
    """Horas semanales que el modelo de la USM reconoce a la docencia de un perfil (carga nominal)."""
    doc_ = d["docencia"]
    cursos = sum(USM["asignatura_nominal"] / a.get("profesores", 1) for a in doc_["asignaturas"])
    tes = sum(USM["tesis"][k] * doc_.get("tesistas", {}).get(k, 0) for k in USM["tesis"])
    return cursos + tes


def usm_investigacion(d):
    """Horas semanales que el modelo de la USM reconoce a la investigación de un perfil."""
    inv_ = d.get("investigacion", {})
    proy = inv_.get("proyectosExternosResponsable", 0) * USM["proyecto_externo_responsable"] \
        + inv_.get("proyectosCoinvestigador", 0) * USM["proyecto_coinvestigador"]
    arts = inv_.get("articulos", 0) + inv_.get("articulosCoautor", 0) + inv_.get("articulosBajaExigencia", 0)
    if inv_.get("proyectosExternosResponsable", 0) > 0:
        arts = max(arts - 1, 0)  # la primera publicación comprometida va incluida en el proyecto
    return proy + arts * USM["articulo_semanal"] / USM["autores_por_articulo"]


def dist(f, muestras=MC):
    """Media exacta (nivel "media") e intervalo de 90 % sobre las muestras."""
    x = np.array([f(R) for R in muestras])
    return {"media": float(f(RMEDIA)), "p05": float(np.percentile(x, 5)), "p95": float(np.percentile(x, 95))}


# ---------------------------------------------------------------- figura: costo de los mínimos

r = RES["minimo"]
fig, ax = plt.subplots(figsize=(ANCHO * 0.62, 3.3))
ax.axhspan(14, JORNADA, color="#f1efe8", zorder=0)
ax.axhline(JORNADA, color=TINTA, lw=0.9)
ax.axhline(14, color=TINTA2, lw=0.7, ls="--")
ax.text(1.62, JORNADA + 0.6, "jornada de 40 h", fontsize=7.5, color=TINTA, va="bottom")
ax.text(1.62, 14 - 0.6, "mínimos: 14 h", fontsize=7.5, color=TINTA2, va="top")
ax.text(1.62, 22, f"{LIBRES:.0f} h de\nlibre disposición\nsegún el modelo", ha="left", va="center", fontsize=7.5, color=TINTA2)
apilar(ax, 0, partes_rec(r["credito"]), 0.5)
top = apilar(ax, 1, partes_real(r), 0.5)
bigote(ax, 1.33, r, capsize=3)
# Referencia USM: horas que su modelo reconoce a la misma docencia
usm_min = usm_docencia(POR_ID["minimo"]["datos"])
ax.plot([-0.3, 1.25], [usm_min, usm_min], color=USM_COLOR, lw=1.2, ls=(0, (4, 2)))
ax.text(-0.45, usm_min + 0.5, f"docencia USM: {es(usm_min)} h", fontsize=6.8, color=USM_COLOR, va="bottom", ha="left")
ax.text(1.40, r["total"]["media"], "intervalo\n90 %", fontsize=6.5, color=TINTA2, va="center", ha="left")
ax.text(0, r["credito"]["total"] + 0.8, es(r["credito"]["total"]), ha="center", fontsize=8, color=TINTA)
ax.text(1.0, top + 0.8, es(top), ha="center", fontsize=8, color=TINTA)
ax.set_xticks([0, 1], ["Horas reconocidas\npor el modelo", "Horas reales\n(media)"])
ax.set_xlim(-0.5, 2.6)
ax.set_ylim(0, 46)
ax.set_ylabel("horas por semana lectiva")
ax.grid(False)
leyenda(ax, loc="upper left", bbox_to_anchor=(0.0, -0.18), ncol=3)
guardar(fig, "fig_minimos")

# ---------------------------------------------------------------- figura: perfiles

ids = ["minimo", "docente", "gestion", "investigador"]
CORTO = {"minimo": "Mínimo\nexigible", "docente": "Docencia\nintensiva", "gestion": "Jefatura\nde carrera",
         "investigador": "Investigación\nactiva", "baja_produccion": "Producción\nmínima"}
fig, ax = plt.subplots(figsize=(ANCHO, 3.4))
ax.axhspan(JORNADA * 0.9, JORNADA * 1.1, color="#f1efe8", zorder=0)
ax.axhline(JORNADA, color=TINTA, lw=0.9)
ax.text(-0.42, JORNADA * 1.1 + 0.5, "jornada de 40 h ± 10 %", fontsize=7.5, color=TINTA2, ha="left", va="bottom")
for i, k in enumerate(ids):
    rr = RES[k]
    apilar(ax, i - 0.19, partes_rec(rr["credito"]), 0.34, etiquetar=False)
    apilar(ax, i + 0.19, partes_real(rr), 0.34, etiquetar=False)
    bigote(ax, i + 0.41, rr, capsize=2)
    ax.text(i - 0.19, rr["credito"]["total"] + 0.8, es(rr["credito"]["total"]), ha="center", fontsize=7, color=TINTA)
    ax.text(i + 0.19, rr["total"]["media"] + 0.8, es(rr["total"]["media"]), ha="center", fontsize=7, color=TINTA)
ax.set_xticks(range(len(ids)), [CORTO[k] + "\nreconocidas · reales" for k in ids])
ax.set_ylabel("horas por semana lectiva")
ax.set_ylim(0, 78)
leyenda(ax, loc="upper left", ncol=3)
guardar(fig, "fig_perfiles")

# ---------------------------------------------------------------- figura: una asignatura más

base = POR_ID["investigador"]["datos"]
curso = {"bloques": 4, "alumnos": 40, "profesores": 1, "nivel": "pregrado", "tipo": "estandar"}
ks = list(range(0, 5))
barrido = []
for k in ks:
    d = copy.deepcopy(base)
    d["docencia"]["asignaturas"] = [a for a in d["docencia"]["asignaturas"] if a["nivel"] == "postgrado"] + [dict(curso) for _ in range(k)]
    rk = C.resumen(d, MC, P)
    barrido.append((rk["credito"]["total"], rk["total"]))
cred_k = [b[0] for b in barrido]
real_k = [b[1]["media"] for b in barrido]
fig, ax = plt.subplots(figsize=(ANCHO * 0.75, 3.0))
ax.fill_between(ks, [b[1]["p05"] for b in barrido], [b[1]["p95"] for b in barrido], color=COLOR["docencia"], alpha=0.15, lw=0)
ax.plot(ks, real_k, color=COLOR["docencia"], lw=2, marker="o", ms=5, label="Horas reales (media; banda: intervalo 90 %)")
ax.plot(ks, cred_k, color=TINTA2, lw=2, marker="s", ms=5, label="Horas reconocidas por el modelo")
ax.axhline(JORNADA, color=TINTA, lw=0.9)
ax.text(-0.1, JORNADA + 1, "jornada de 40 h", ha="left", va="bottom", fontsize=7.5)
for k, (c_, r_) in enumerate(zip(cred_k, real_k)):
    ax.text(k, r_ + 2.2, es(r_), ha="center", fontsize=7, color=TINTA)
    ax.text(k, c_ - 5.5, es(c_), ha="center", fontsize=7, color=TINTA2)
ax.set_xticks(ks)
ax.set_xlabel("asignaturas de pregrado de 40 estudiantes (además del curso de postgrado)")
ax.set_ylabel("horas por semana lectiva")
ax.set_ylim(0, max(b[1]["p95"] for b in barrido) + 8)
ax.legend(frameon=False, loc="upper left")
guardar(fig, "fig_barrido")

# ---------------------------------------------------------------- figura: una asignatura según matrícula

Ns = np.arange(1, 61)
casos = [("pregrado", "estandar", "Pregrado, ya impartida", COLOR["docencia"]),
         ("postgrado", "estandar", "Postgrado, ya impartida", COLOR["investigacion"]),
         ("pregrado", "nueva", "Pregrado, primera vez", COLOR["vinculacion"])]
fig, ax = plt.subplots(figsize=(ANCHO * 0.75, 3.0))
for nivel, tipo, et, col in casos:
    medias, lo, hi = [], [], []
    for n in Ns:
        dd = dist(lambda R: C.horas_asignatura({"bloques": 4, "alumnos": int(n), "nivel": nivel, "tipo": tipo}, R))
        medias.append(dd["media"]); lo.append(dd["p05"]); hi.append(dd["p95"])
    ax.fill_between(Ns, lo, hi, color=col, alpha=0.12, lw=0)
    ax.plot(Ns, medias, color=col, lw=2, label=et)
ax.plot(Ns, [C.credito_asignatura({"bloques": 4, "alumnos": int(n)}) for n in Ns], color=TINTA, lw=2, label="Horas reconocidas (todas)")
ax.axhline(USM["asignatura_nominal"], color=USM_COLOR, lw=1.4, ls=(0, (4, 2)), label="Carga nominal USM (10 h)")
ax.axvline(40, color=TINTA2, lw=0.7, ls="--")
ax.text(40.8, 25, "capacidad habitual\nde sala (40)", fontsize=7, color=TINTA2, va="bottom")
ax.set_xlim(1, 60)
ax.set_xlabel("estudiantes inscritos")
ax.set_ylabel("horas por semana lectiva")
ax.set_ylim(0, None)
ax.legend(frameon=False, loc="upper left")
guardar(fig, "fig_asignatura")

# ---------------------------------------------------------------- figura: tesis

niveles_t = ["pregrado", "magister", "doctorado"]
nombres_t = {"pregrado": "Titulación", "magister": "Magíster", "doctorado": "Doctorado"}
TES = {t: dist(lambda R, t=t: R["docencia"]["tesis_horas_anio"][t] / SEM, M) for t in niveles_t}
fig, ax = plt.subplots(figsize=(ANCHO * 0.75, 2.8))
for i, t in enumerate(niveles_t):
    d_ = TES[t]
    ax.barh(i + 0.26, USM["tesis"][t], 0.24, color=USM_COLOR, edgecolor="white")
    ax.text(USM["tesis"][t] + 0.05, i + 0.26, es(USM["tesis"][t], 2), va="center", fontsize=7, color=USM_COLOR)
    ax.barh(i, d_["media"], 0.24, color=COLOR["docencia"], edgecolor="white")
    ax.errorbar(d_["media"], i, xerr=[[d_["media"] - d_["p05"]], [d_["p95"] - d_["media"]]], color=TINTA, capsize=2.5, lw=0.8, fmt="none")
    ax.barh(i - 0.26, 35 / 60, 0.24, color=TINTA2, edgecolor="white")
    ax.text(d_["p95"] + 0.05, i, es(d_["media"], 2), va="center", fontsize=7)
    ax.text(35 / 60 + 0.05, i - 0.26, "0,58", va="center", fontsize=7, color=TINTA2)
ax.set_yticks(range(3), [nombres_t[t] for t in niveles_t])
ax.set_xlabel("horas por semana y por estudiante")
ax.grid(axis="x", color="#e4e3df", lw=0.6)
ax.grid(axis="y", visible=False)
ax.legend(handles=[Patch(color=TINTA2, label="Horas reconocidas por el modelo PUCV"), Patch(color=COLOR["docencia"], label="Horas reales (media; intervalo 90 %)"),
                   Patch(color=USM_COLOR, label="Horas reconocidas por la USM")],
          frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=2, fontsize=7)
guardar(fig, "fig_tesis")

# ---------------------------------------------------------------- figura: dos investigadores

comp = ["investigador", "baja_produccion"]
fig, ax = plt.subplots(figsize=(ANCHO * 0.62, 2.8))
for i, k in enumerate(comp):
    rr = RES[k]
    u_ = usm_investigacion(POR_ID[k]["datos"])
    ax.bar(i - 0.26, rr["credito"]["investigacion"], 0.24, color=TINTA2, edgecolor="white")
    ax.bar(i, rr["investigacion"]["media"], 0.24, color=COLOR["investigacion"], edgecolor="white")
    ax.bar(i + 0.26, u_, 0.24, color=USM_COLOR, edgecolor="white")
    bigote(ax, i, rr, clave="investigacion", capsize=2.5)
    ax.text(i - 0.26, rr["credito"]["investigacion"] + 0.7, es(rr["credito"]["investigacion"]), ha="center", fontsize=7)
    ax.text(i, rr["investigacion"]["p95"] + 0.7, es(rr["investigacion"]["media"]), ha="center", fontsize=7)
    ax.text(i + 0.26, u_ + 0.7, es(u_), ha="center", fontsize=7, color=USM_COLOR)
ax.set_xticks(range(2), [CORTO[k].replace("\n", " ") for k in comp])
ax.set_ylabel("horas semanales de investigación")
ax.set_ylim(0, 42)
ax.legend(handles=[Patch(color=TINTA2, label="Horas reconocidas por el modelo PUCV"), Patch(color=COLOR["investigacion"], label="Horas reales (media; intervalo 90 %)"),
                   Patch(color=USM_COLOR, label="Horas reconocidas por la USM")],
          frameon=False, loc="upper right", fontsize=7)
guardar(fig, "fig_investigadores")

# ---------------------------------------------------------------- tablas

def iv(d, dec=1):
    return f"{es(d['p05'], dec)}--{es(d['p95'], dec)}"


def tabla_minimo():
    r = RES["minimo"]
    filas = []
    for d in C.DIMENSIONES:
        c_ = r["credito"][d]
        filas.append(f"{ETIQUETA[d]} & {es(c_)} & {es(r[d]['media'])} & {iv(r[d])} & {es(r[d]['media'] / c_)} \\\\")
    s = r["servicio_no_reconocido"]
    filas.append(f"Servicio no reconocido & --- & {es(s['media'])} & {iv(s)} & --- \\\\")
    filas.append("\\midrule")
    filas.append(f"Total & {es(r['credito']['total'])} & {es(r['total']['media'])} & {iv(r['total'])} & {es(r['total']['media'] / r['credito']['total'])} \\\\")
    return ("\\begin{tabular}{lrrcr}\n\\toprule\n"
            " & Horas & \\multicolumn{2}{c}{Horas reales} & Reales por hora \\\\\n\\cmidrule(lr){3-4}\n"
            "Dimensión & reconocidas & media & intervalo 90\\,\\% & reconocida \\\\\n\\midrule\n"
            + "\n".join(filas) + "\n\\bottomrule\n\\end{tabular}\n")


def tabla_perfiles():
    filas = []
    for k in ids + ["baja_produccion"]:
        rr = RES[k]
        cumple = "sí" if all(rr["credito"]["cumple"].values()) else "no"
        filas.append(f"{POR_ID[k]['nombre']} & {es(rr['credito']['total'])} & {cumple} & {es(rr['total']['media'])} & {iv(rr['total'])} & "
                     f"{es(rr['libres']['media'])} \\\\")
    return ("\\begin{tabular}{lrcrcr}\n\\toprule\n"
            " & Horas & ¿Cumple los & \\multicolumn{2}{c}{Horas reales} & Horas libres \\\\\n\\cmidrule(lr){4-5}\n"
            "Perfil & reconocidas & mínimos? & media & intervalo 90\\,\\% & efectivas \\\\\n\\midrule\n"
            + "\n".join(filas) + "\n\\bottomrule\n\\end{tabular}\n")


CASOS_ASIG = [("pregrado", "estandar", 40, "Pregrado, 40 estudiantes"),
              ("pregrado", "estandar", 20, "Pregrado, 20 estudiantes"),
              ("pregrado", "estandar", 5, "Pregrado optativo, 5 estudiantes"),
              ("postgrado", "estandar", 5, "Postgrado, 5 estudiantes"),
              ("pregrado", "nueva", 40, "Pregrado, 40 estudiantes, primera vez"),
              ("postgrado", "nueva", 5, "Postgrado, 5 estudiantes, primera vez")]


def tabla_asignaturas():
    filas = []
    for nivel, tipo, n_, et in CASOS_ASIG:
        a = {"bloques": 4, "alumnos": n_, "nivel": nivel, "tipo": tipo}
        cr_ = C.credito_asignatura(a)
        d_ = dist(lambda R: C.horas_asignatura(a, R), M)
        filas.append(f"{et} & {es(cr_, 2)} & {es(d_['media'])} & {iv(d_)} & {es(d_['media'] / cr_)} & {es(USM['asignatura_nominal'], 0)} \\\\")
    return ("\\begin{tabular}{lrrcrr}\n\\toprule\n"
            " & Horas & \\multicolumn{2}{c}{Horas reales} & Reales por hora & Carga \\\\\n\\cmidrule(lr){3-4}\n"
            "Asignatura de cuatro bloques semanales & reconocidas & media & intervalo 90\\,\\% & reconocida & USM \\\\\n\\midrule\n"
            + "\n".join(filas) + "\n\\bottomrule\n\\end{tabular}\n")


def tabla_investigadores():
    filas = []
    for k in comp:
        rr = RES[k]
        c_, m_ = rr["credito"]["investigacion"], rr["investigacion"]["media"]
        filas.append(f"{POR_ID[k]['nombre']} & {es(c_)} & {es(m_)} & {iv(rr['investigacion'])} & {es(c_ / m_, 2)} \\\\")
    return ("\\begin{tabular}{lrrcr}\n\\toprule\n"
            " & Horas & \\multicolumn{2}{c}{Horas reales} & Horas reconocidas \\\\\n\\cmidrule(lr){3-4}\n"
            "Perfil & reconocidas & media & intervalo 90\\,\\% & por hora real \\\\\n\\midrule\n"
            + "\n".join(filas) + "\n\\bottomrule\n\\end{tabular}\n")


def _fmt_rango(x):
    f = lambda v: es(v, 2 if v % 1 else 0)
    return f"{f(x['bajo'])} / {f(x['central'])} / {f(x['alto'])}"


NOMBRES_PARAM = {
    ("docencia", "preparacion_por_hora_contacto", "pregrado"): "Preparación por hora de clase, pregrado ya impartido",
    ("docencia", "preparacion_por_hora_contacto", "postgrado"): "Preparación por hora de clase, postgrado ya impartido",
    ("docencia", "preparacion_por_hora_contacto", "nueva"): "Preparación por hora de clase, asignatura nueva",
    ("docencia", "preparacion_por_hora_contacto", "seccion_paralela"): "Preparación por hora de clase, sección paralela",
    ("docencia", "preparacion_por_hora_contacto", "laboratorio"): "Preparación por hora de laboratorio",
    ("docencia", "evaluacion_por_estudiante_semestre", "pregrado"): "Evaluación y atención por estudiante y semestre, pregrado (h)",
    ("docencia", "evaluacion_por_estudiante_semestre", "postgrado"): "Evaluación y atención por estudiante y semestre, postgrado (h)",
    ("docencia", "coordinacion_semestre", "base"): "Coordinación por asignatura y semestre (h)",
    ("docencia", "coordinacion_semestre", "por_estudiante"): "Coordinación por estudiante y semestre (h)",
    ("docencia", "tesis_horas_anio", "pregrado"): "Guía de titulación (h/año)",
    ("docencia", "tesis_horas_anio", "magister"): "Guía de tesis de magíster (h/año)",
    ("docencia", "tesis_horas_anio", "doctorado"): "Guía de tesis doctoral (h/año)",
    ("investigacion", "proyectosExternosResponsable"): "Proyecto externo como responsable (h/sem)",
    ("investigacion", "proyectosInternosResponsable"): "Proyecto interno como responsable (h/sem)",
    ("investigacion", "proyectosCoinvestigador"): "Coinvestigación (h/sem)",
    ("investigacion", "articulos"): "Artículo como autor principal (h)",
    ("investigacion", "articulosBajaExigencia"): "Artículo en revista de baja exigencia (h)",
    ("investigacion", "articulosCoautor"): "Artículo como coautor (h)",
    ("investigacion", "fraccion_superpuesta_con_proyecto"): "Fracción de la escritura contenida en un proyecto propio",
    ("investigacion", "proyectosNoAdjudicados"): "Postulación no adjudicada (h)",
    ("investigacion", "arbitrajes"): "Referato de un artículo (h)",
    ("gestion", "directorUnidad"): "Director de unidad (h/sem)",
    ("gestion", "decano"): "Decano (h/sem)",
    ("gestion", "jefeCarrera"): "Jefe de carrera (h/sem)",
    ("gestion", "directorPostgrado"): "Director de programa de postgrado (h/sem)",
    ("gestion", "jefeInvestigacion"): "Jefe de investigación (h/sem)",
    ("gestion", "jefeExtension"): "Jefe de extensión (h/sem)",
    ("gestion", "editorRevista"): "Editor de revista (h/sem)",
    ("gestion", "comisiones"): "Miembro de comisión (h/sem)",
    ("servicio_no_reconocido", "correo_administracion"): "Correo y trámites (h/año)",
    ("servicio_no_reconocido", "examen_tesis"): "Examen de tesis (h/año)",
}


def tabla_parametros():
    filas = []
    for ruta, nombre in NOMBRES_PARAM.items():
        x = P
        for k in ruta:
            x = x[k]
        fuentes = ", ".join(x.get("fuentes", []))
        cita = f"\\citet{{{fuentes}}}" if fuentes else "supuesto"
        filas.append(f"{nombre} & {_fmt_rango(x)} & {cita} \\\\")
    return ("\\begin{longtable}{p{0.42\\textwidth}cp{0.33\\textwidth}}\n\\toprule\n"
            "Parámetro & bajo / moda / alto & Fuente \\\\\n\\midrule\n\\endhead\n"
            + "\n".join(filas) + "\n\\bottomrule\n\\end{longtable}\n")


(TAB / "tab_minimo.tex").write_text(tabla_minimo(), encoding="utf-8")
(TAB / "tab_perfiles.tex").write_text(tabla_perfiles(), encoding="utf-8")
(TAB / "tab_asignaturas.tex").write_text(tabla_asignaturas(), encoding="utf-8")
(TAB / "tab_investigadores.tex").write_text(tabla_investigadores(), encoding="utf-8")
(TAB / "tab_parametros.tex").write_text(tabla_parametros(), encoding="utf-8")

# ---------------------------------------------------------------- cifras para el texto


def macro(nombre, valor):
    valor = str(valor)
    if valor.startswith("-"):
        valor = "\\ensuremath{-}" + valor[1:]
    return f"\\newcommand{{\\{nombre}}}{{{valor}}}"


ug40 = {"bloques": 4, "alumnos": 40, "nivel": "pregrado", "tipo": "estandar"}
ug1 = {"bloques": 4, "alumnos": 1, "nivel": "pregrado", "tipo": "estandar"}
ug5 = {"bloques": 4, "alumnos": 5, "nivel": "pregrado", "tipo": "estandar"}
pg5 = {"bloques": 4, "alumnos": 5, "nivel": "postgrado", "tipo": "estandar"}
A = {k: dist(lambda R, a=a: C.horas_asignatura(a, R), M) for k, a in
     {"ug40": ug40, "ug1": ug1, "ug5": ug5, "pg5": pg5, "ug40n": {**ug40, "tipo": "nueva"}, "pg5n": {**pg5, "tipo": "nueva"}}.items()}
A["ug40a"] = dist(lambda R: C.horas_asignatura(ug40, R, "anual"), M)
mn, inv, doc, ges, baja = (RES[k] for k in ("minimo", "investigador", "docente", "gestion", "baja_produccion"))
rec_hora_inv = inv["credito"]["investigacion"] / inv["investigacion"]["media"]
rec_hora_baja = baja["credito"]["investigacion"] / baja["investigacion"]["media"]

dos = copy.deepcopy(POR_ID["investigador"]["datos"]); dos["investigacion"]["proyectosExternosResponsable"] = 2
tres = copy.deepcopy(POR_ID["investigador"]["datos"]); tres["investigacion"]["proyectosExternosResponsable"] = 3

lineas = [
    "% Generado por simulador/generar.py. No editar a mano.",
    macro("NMonteCarlo", f"{N_MC:,}".replace(",", ".")),
    macro("LibresNominales", es(LIBRES, 0)),
    # una asignatura
    macro("AsigUGRec", es(C.credito_asignatura(ug40), 2)),
    macro("AsigUGReal", es(A["ug40"]["media"])),
    macro("AsigUGRealLo", es(A["ug40"]["p05"])),
    macro("AsigUGRealHi", es(A["ug40"]["p95"])),
    macro("AsigUGCociente", es(A["ug40"]["media"] / C.credito_asignatura(ug40))),
    macro("AsigUGAnual", es(A["ug40a"]["media"])),
    macro("AsigUGNuevaReal", es(A["ug40n"]["media"])),
    macro("AsigUnoRec", es(C.credito_asignatura(ug1), 2)),
    macro("AsigUnoReal", es(A["ug1"]["media"])),
    macro("AsigCincoRec", es(C.credito_asignatura(ug5), 2)),
    macro("AsigCincoReal", es(A["ug5"]["media"])),
    macro("AsigPGRec", es(C.credito_asignatura(pg5), 2)),
    macro("AsigPGReal", es(A["pg5"]["media"])),
    macro("AsigPGCociente", es(A["pg5"]["media"] / C.credito_asignatura(pg5))),
    macro("AsigPGNuevaReal", es(A["pg5n"]["media"])),
    # Baremo de la Escuela de Economía de la Universidad de Queensland (2024) aplicado al mismo curso:
    # 4 h por hora de clase, 98,7 h de preparación, 10,8 h por cada 50 estudiantes, 1 h por estudiante, 17,3 h de coordinación.
    macro("UQSemestre", es(4 * 35 / 60 * 17 * 4 + 98.7 + 10.8 + 40 * 1 + 17.33, 0)),
    macro("UQSemana", es((4 * 35 / 60 * 17 * 4 + 98.7 + 10.8 + 40 * 1 + 17.33) / 17)),
    macro("PUCVSemestre", es(C.credito_asignatura(ug40) * 17, 0)),
    macro("NuestraSemestre", es(A["ug40"]["media"] * 17, 0)),
    macro("MargEstudianteSem", es(4 * 35 / 60 * 0.01 * 17, 2)),
    macro("CursosParaMinimo", es(8 / C.credito_asignatura(ug40))),
    macro("CursosPGParaMinimo", es(8 / C.credito_asignatura(pg5))),
    # referencia USM (Decreto de Rectoría 258/2015)
    macro("USMAsig", es(USM["asignatura_nominal"], 0)),
    macro("USMSemestre", es(USM["asignatura_nominal"] * 17, 0)),
    macro("USMMinDoc", es(usm_docencia(POR_ID["minimo"]["datos"]))),
    macro("USMInvInv", es(usm_investigacion(POR_ID["investigador"]["datos"]))),
    macro("USMBajaInv", es(usm_investigacion(POR_ID["baja_produccion"]["datos"]))),
    macro("USMInvPorHora", es(usm_investigacion(POR_ID["investigador"]["datos"]) / inv["investigacion"]["media"], 2)),
    macro("USMBajaPorHora", es(usm_investigacion(POR_ID["baja_produccion"]["datos"]) / baja["investigacion"]["media"], 2)),
    macro("USMAutores", es(USM["autores_por_articulo"], 0)),
    macro("USMFactor", es((usm_investigacion(POR_ID["baja_produccion"]["datos"]) / baja["investigacion"]["media"])
                          / (usm_investigacion(POR_ID["investigador"]["datos"]) / inv["investigacion"]["media"]))),
    # tesis
    macro("TesisRecAnio", es(35 / 60 * SEM, 0)),
    macro("TesisDocReal", es(TES["doctorado"]["media"], 2)),
    macro("TesisDocCociente", es(TES["doctorado"]["media"] / (35 / 60))),
    # perfil mínimo
    macro("MinRec", es(mn["credito"]["total"])),
    macro("MinDocRec", es(mn["credito"]["docencia"], 2)),
    macro("MinReal", es(mn["total"]["media"])),
    macro("MinRealLo", es(mn["total"]["p05"])),
    macro("MinRealHi", es(mn["total"]["p95"])),
    macro("MinDocReal", es(mn["docencia"]["media"])),
    macro("MinCosto", es(mn["costo_minimos"]["media"])),
    macro("MinLibres", es(mn["libres"]["media"])),
    macro("MinLibresLo", es(mn["libres"]["p05"])),
    macro("MinLibresHi", es(mn["libres"]["p95"])),
    macro("MinConsumo", es(LIBRES - mn["libres"]["media"])),
    macro("MinProbMitad", pct(mn["prob_libres_menor_mitad"])),
    macro("MinServicio", es(mn["servicio_no_reconocido"]["media"])),
    # investigación activa y producción mínima
    macro("InvRec", es(inv["credito"]["total"])),
    macro("InvInvRec", es(inv["credito"]["investigacion"])),
    macro("InvInvReal", es(inv["investigacion"]["media"])),
    macro("InvArtReal", es(C.horas_reales(POR_ID["investigador"]["datos"], RMEDIA)["investigacion_desglose"]["articulos"])),
    macro("InvReal", es(inv["total"]["media"])),
    macro("InvRealLo", es(inv["total"]["p05"])),
    macro("InvRealHi", es(inv["total"]["p95"])),
    macro("InvProbSobre", pct(inv["prob_total_sobre_jornada"])),
    macro("InvLibres", es(inv["libres"]["media"])),
    macro("BajaRec", es(baja["credito"]["total"])),
    macro("BajaInvRec", es(baja["credito"]["investigacion"])),
    macro("BajaInvReal", es(baja["investigacion"]["media"])),
    macro("BajaReal", es(baja["total"]["media"])),
    macro("InvRecPorHora", es(rec_hora_inv, 2)),
    macro("BajaRecPorHora", es(rec_hora_baja, 2)),
    macro("FactorRecPorHora", es(rec_hora_baja / rec_hora_inv)),
    macro("DosProyectosRec", es(C.credito_pucv(dos)["total"])),
    macro("TresProyectosRec", es(C.credito_pucv(tres)["total"])),
    # docencia intensiva y jefatura
    macro("DocRec", es(doc["credito"]["total"])),
    macro("DocReal", es(doc["total"]["media"])),
    macro("DocRealLo", es(doc["total"]["p05"])),
    macro("DocRealHi", es(doc["total"]["p95"])),
    macro("DocProbSobre", pct(doc["prob_total_sobre_jornada"])),
    macro("GesRec", es(ges["credito"]["total"])),
    macro("GesDocRec", es(ges["credito"]["docencia"], 2)),
    macro("GesReal", es(ges["total"]["media"])),
    macro("GesProbSobre", pct(ges["prob_total_sobre_jornada"])),
    # barrido
    macro("BarridoPasoReal", es(real_k[1] - real_k[0])),
    macro("BarridoPasoRec", es(cred_k[1] - cred_k[0])),
    macro("BarridoRecTres", es(cred_k[3])),
    macro("BarridoRealTres", es(real_k[3])),
]
(DOC / "numeros.tex").write_text("\n".join(lineas) + "\n", encoding="utf-8")

# ---------------------------------------------------------------- web

(WEB / "parametros.js").write_text(
    "// Generado por simulador/generar.py desde parametros.json. No editar a mano.\n"
    "(function (root) {\n  const P = " + json.dumps(P, ensure_ascii=False, indent=2) + ";\n"
    "  if (typeof module === \"object\" && module.exports) module.exports = P;\n"
    "  else root.PUCVParametros = P;\n})(typeof globalThis !== \"undefined\" ? globalThis : this);\n",
    encoding="utf-8")
(WEB / "perfiles.js").write_text(
    "// Generado por simulador/generar.py desde perfiles.json. No editar a mano.\n"
    "(function (root) {\n  const PERFILES = " + json.dumps(PERFILES, ensure_ascii=False, indent=2) + ";\n"
    "  if (typeof module === \"object\" && module.exports) module.exports = PERFILES;\n"
    "  else root.PUCVPerfiles = PERFILES;\n})(typeof globalThis !== \"undefined\" ? globalThis : this);\n",
    encoding="utf-8")
fixtures = []
for p in PERFILES:
    for modo in ("lectiva", "anual"):
        for n in C.NIVELES + ("media",):
            re_ = C.horas_reales(p["datos"], C.resolver(P, n), modo)
            fixtures.append({"perfil": p["id"], "modo": modo, "nivel": n, "credito": C.credito_pucv(p["datos"])["total"],
                             "real": {k: re_[k] for k in C.CLAVES_RESUMEN}})
(WEB / "fixtures.json").write_text(json.dumps({"perfiles": PERFILES, "casos": fixtures}, ensure_ascii=False, indent=1), encoding="utf-8")

print("Listo:", ", ".join(sorted(x.name for x in FIG.glob("*.pdf"))))
for k in ids + ["baja_produccion"]:
    rr = RES[k]
    print(f"  {k:16s} reconocidas {rr['credito']['total']:5.1f}  reales {rr['total']['media']:5.1f} "
          f"({rr['total']['p05']:5.1f}–{rr['total']['p95']:5.1f})  libres {rr['libres']['media']:5.1f}")
