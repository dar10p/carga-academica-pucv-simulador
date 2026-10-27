// Horas reales: port en JavaScript de simulador/carga.py (horas_reales y resolver).
// Requiere parametros.js (generado desde parametros.json) y model.js (réplica PUCV).
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PUCVReal = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const NIVELES = ["bajo", "central", "alto"];
  const PESOS_VINCULACION = {
    lineasVinculacion: 1, asistenciaTecnica: 2, formacionContinua: 3, direccionDivulgacion: 3,
    presenciaSociedad: 0.5, politicasPublicas: 2, difusionPrePostgrado: 1,
  };

  function num(v, { entero = false, max = Infinity } = {}) {
    let n = v === true ? 1 : Number(v);
    if (!Number.isFinite(n) || n < 0) n = 0;
    if (entero) n = Math.floor(n);
    return Math.min(n, max);
  }

  const esRango = x => x && typeof x === "object" && NIVELES.every(n => n in x);

  function resolver(P, nivel = "central") {
    const rec = x => {
      if (esRango(x)) return nivel === "media"
        ? (Number(x.bajo) + Number(x.central) + Number(x.alto)) / 3  // media exacta de la triangular
        : Number(x[nivel]);
      if (Array.isArray(x)) return x.map(rec);
      if (x && typeof x === "object") {
        const out = {};
        for (const [k, v] of Object.entries(x)) if (!["fuentes", "nota", "unidad"].includes(k)) out[k] = rec(v);
        return out;
      }
      return x;
    };
    return rec(P);
  }

  function cargos(gestion = {}) {
    const sel = new Set(Array.isArray(gestion.cargos) ? gestion.cargos : []);
    if (sel.has("jefeDocenciaConApoyo") && sel.has("jefeDocenciaSinApoyo")) sel.delete("jefeDocenciaConApoyo");
    return sel;
  }

  function horasAsignatura(a, R, modo = "lectiva") {
    const cal = R.calendario, d = R.docencia;
    const nivel = a.nivel || "pregrado";
    const tipo = a.tipo || "estandar";
    const prep = d.preparacion_por_hora_contacto[tipo === "estandar" ? nivel : tipo];
    const n = num(a.alumnos);
    const contacto = num(a.bloques ?? a.claves) * cal.minutos_bloque / 60;
    const profesores = Math.max(1, num(a.profesores ?? 1, { entero: true }));
    const semestral = d.evaluacion_por_estudiante_semestre[nivel] * n
      + d.coordinacion_semestre.base + d.coordinacion_semestre.por_estudiante * n;
    let h = (contacto * (1 + prep) + semestral / cal.semanas_lectivas_semestre) / profesores;
    if (modo === "anual") h *= cal.semanas_lectivas_anio / cal.semanas_laborales_anio;
    return h;
  }

  function horasReales(perfil, R, modo = "lectiva") {
    const sem = R.calendario.semanas_laborales_anio;
    const doc = perfil.docencia || {};
    const asignaturas = (doc.asignaturas || []).reduce((s, a) => s + horasAsignatura(a, R, modo), 0);
    let tes = doc.tesistas || {};
    if (typeof tes !== "object") tes = { pregrado: tes };
    const guias = ["pregrado", "magister", "doctorado"].reduce((s, k) => s + num(tes[k]) * R.docencia.tesis_horas_anio[k] / sem, 0);
    const docencia = asignaturas + guias + num(doc.talleres) * R.docencia.talleres + (doc.diplomado ? R.docencia.diplomado : 0);

    const I = R.investigacion, inv = perfil.investigacion || {};
    const tieneProyecto = num(inv.proyectosExternosResponsable) + num(inv.proyectosInternosResponsable) > 0;
    const libre = tieneProyecto ? 1 - I.fraccion_superpuesta_con_proyecto : 1;
    const desglose = {
      proyectos: num(inv.proyectosExternosResponsable) * I.proyectosExternosResponsable
        + num(inv.proyectosInternosResponsable) * I.proyectosInternosResponsable
        + num(inv.proyectosCoinvestigador) * I.proyectosCoinvestigador,
      articulos: libre * (num(inv.articulos) * I.articulos + num(inv.articulosBajaExigencia) * I.articulosBajaExigencia
        + num(inv.articulosCoautor) * I.articulosCoautor) / sem,
      propuestas: num(inv.proyectosNoAdjudicados) * I.proyectosNoAdjudicados / sem,
      otras: num(inv.proyectosInnovacionDocente) * I.proyectosInnovacionDocente + num(inv.otrasInvestigaciones) * I.otrasInvestigaciones,
      arbitrajes: num(inv.arbitrajes) * I.arbitrajes / sem,
    };
    if ("horasDeclaradasProyecto" in inv) desglose.proyectos = num(inv.horasDeclaradasProyecto);
    const investigacion = Object.values(desglose).reduce((a, b) => a + b, 0);

    const f = R.vinculacion.factor_por_actividad, vin = perfil.vinculacion || {};
    const vinculacion = Object.entries(PESOS_VINCULACION).reduce((s, [k, p]) => s + num(vin[k]) * p * f, 0);

    const gestion = [...cargos(perfil.gestion)].reduce((s, k) => s + (R.gestion[k] ?? 0), 0);
    const S = R.servicio_no_reconocido;
    const servicio_no_reconocido = (S.correo_administracion + S.examen_tesis) / sem;
    const otras = num(perfil.otrasActividades, { max: 6 });
    const total = docencia + investigacion + vinculacion + gestion + servicio_no_reconocido + otras;
    return { docencia, investigacion, vinculacion, gestion, servicio_no_reconocido, otras, total, asignaturas, guias, investigacion_desglose: desglose };
  }

  return { NIVELES, resolver, horasAsignatura, horasReales };
});
