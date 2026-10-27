(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PUCVCarga = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const MINIMOS = Object.freeze({
    docencia: 8,
    investigacion: 2,
    vinculacion: 2,
    gestion: 2,
  });

  const PESOS_INVESTIGACION = Object.freeze({
    proyectosExternosResponsable: 15,
    proyectosInternosResponsable: 8,
    proyectosCoinvestigador: 5,
    articulos: 4,
    proyectosNoAdjudicados: 2,
    proyectosInnovacionDocente: 4,
    otrasInvestigaciones: 1,
  });

  const PESOS_VINCULACION = Object.freeze({
    lineasVinculacion: 1,
    asistenciaTecnica: 2,
    formacionContinua: 3,
    direccionDivulgacion: 3,
    presenciaSociedad: 0.5,
    politicasPublicas: 2,
    difusionPrePostgrado: 1,
  });

  const CARGOS = Object.freeze({
    consejeroSuperior: { nombre: "Consejero superior", horas: 5 },
    capitular: { nombre: "Capitular", horas: 5 },
    decano: { nombre: "Decano", horas: 20 },
    vicedecano: { nombre: "Vicedecano", horas: 10 },
    secretarioFacultad: { nombre: "Secretario de facultad", horas: 15 },
    directorUnidad: { nombre: "Director de unidad académica, unidad administrativa o centro", horas: 20 },
    secretarioAcademico: { nombre: "Secretario académico", horas: 10 },
    jefeDocenciaConApoyo: { nombre: "Jefe de docencia con apoyo administrativo", horas: 10 },
    jefeDocenciaSinApoyo: { nombre: "Jefe de docencia sin apoyo administrativo", horas: 20 },
    jefeExtension: { nombre: "Jefe de extensión o vinculación con el medio", horas: 6 },
    jefeInvestigacion: { nombre: "Jefe de investigación", horas: 3 },
    directorPostgrado: { nombre: "Director de programa de magíster o doctorado", horas: 6 },
    jefeCarrera: { nombre: "Jefe de carrera de pregrado o equivalente", horas: 6 },
    editorRevista: { nombre: "Editor de revista", horas: 6 },
    comisiones: { nombre: "Participación en comisiones de escuela o facultad", horas: 2 },
    directorCentroClinico: { nombre: "Director de centro clínico", horas: 8 },
    tutorPrimerAno: { nombre: "Tutor académico de primer año", horas: 1 },
    proyectosInstitucionales: { nombre: "Dirección de proyectos institucionales", horas: 10 },
    otraGestion: { nombre: "Otras actividades de gestión acordadas con la dirección", horas: 1 },
  });

  function numero(value, { entero = false, max = Infinity } = {}) {
    let n = Number(value);
    if (!Number.isFinite(n) || n < 0) n = 0;
    if (entero) n = Math.floor(n);
    return Math.min(n, max);
  }

  function calcularAsignatura(asignatura) {
    const alumnos = numero(asignatura?.alumnos);
    const bloques = numero(asignatura?.bloques ?? asignatura?.claves);
    const profesores = Math.max(1, numero(asignatura?.profesores, { entero: true }));
    return (bloques * 35 * (1 + alumnos * 0.01)) / (60 * profesores);
  }

  function calcularDocencia(docencia = {}) {
    const asignaturas = Array.isArray(docencia.asignaturas) ? docencia.asignaturas : [];
    const horasAsignaturas = asignaturas.reduce((suma, item) => suma + calcularAsignatura(item), 0);
    const horasGuias = numero(docencia.tesistas) * 35 / 60;
    const horasTalleres = numero(docencia.talleres) * 1;
    const horasDiplomado = docencia.diplomado ? 2 : 0;
    return {
      asignaturas: horasAsignaturas,
      guias: horasGuias,
      talleres: horasTalleres,
      diplomado: horasDiplomado,
      total: horasAsignaturas + horasGuias + horasTalleres + horasDiplomado,
    };
  }

  function calcularInvestigacion(investigacion = {}) {
    const cantidades = {};
    for (const clave of Object.keys(PESOS_INVESTIGACION)) {
      cantidades[clave] = numero(investigacion[clave], {
        entero: clave !== "articulos",
        max: clave === "articulos" ? 4 : Infinity,
      });
    }

    // Réplica exacta del sitio: solo un proyecto externo responsable bloquea artículos.
    // El texto institucional también menciona proyectos internos; ver README.
    const articulosBloqueados = cantidades.proyectosExternosResponsable > 0;
    if (articulosBloqueados) cantidades.articulos = 0;

    const desglose = {};
    let total = 0;
    for (const [clave, peso] of Object.entries(PESOS_INVESTIGACION)) {
      desglose[clave] = cantidades[clave] * peso;
      total += desglose[clave];
    }
    return { ...desglose, articulosBloqueados, total };
  }

  function calcularVinculacion(vinculacion = {}) {
    const desglose = {};
    let total = 0;
    for (const [clave, peso] of Object.entries(PESOS_VINCULACION)) {
      desglose[clave] = vinculacion[clave] ? peso : 0;
      total += desglose[clave];
    }
    return { ...desglose, total };
  }

  function calcularGestion(gestion = {}) {
    const seleccionados = new Set(Array.isArray(gestion.cargos) ? gestion.cargos : []);
    if (seleccionados.has("jefeDocenciaConApoyo") && seleccionados.has("jefeDocenciaSinApoyo")) {
      seleccionados.delete("jefeDocenciaConApoyo");
    }
    const desglose = {};
    let total = 0;
    for (const [clave, cargo] of Object.entries(CARGOS)) {
      desglose[clave] = seleccionados.has(clave) ? cargo.horas : 0;
      total += desglose[clave];
    }
    return { ...desglose, total };
  }

  function calcularCarga(datos = {}) {
    const docencia = calcularDocencia(datos.docencia);
    const investigacion = calcularInvestigacion(datos.investigacion);
    const vinculacion = calcularVinculacion(datos.vinculacion);
    const gestion = calcularGestion(datos.gestion);
    const totalOficial = docencia.total + investigacion.total + vinculacion.total + gestion.total;
    const otrasActividades = numero(datos.otrasActividades, { max: 6 });
    const totalConOtras = totalOficial + otrasActividades;
    const cumplimientoMinimos = {
      docencia: docencia.total >= MINIMOS.docencia,
      investigacion: investigacion.total >= MINIMOS.investigacion,
      vinculacion: vinculacion.total >= MINIMOS.vinculacion,
      gestion: gestion.total >= MINIMOS.gestion,
    };
    return {
      docencia,
      investigacion,
      vinculacion,
      gestion,
      totalOficial,
      otrasActividades,
      totalConOtras,
      cumplimientoMinimos,
      brecha34: 34 - totalOficial,
      brecha40: 40 - totalConOtras,
    };
  }

  return {
    MINIMOS,
    PESOS_INVESTIGACION,
    PESOS_VINCULACION,
    CARGOS,
    calcularAsignatura,
    calcularDocencia,
    calcularInvestigacion,
    calcularVinculacion,
    calcularGestion,
    calcularCarga,
  };
});
