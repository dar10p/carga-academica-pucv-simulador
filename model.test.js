"use strict";

const assert = require("node:assert/strict");
const model = require("./model.js");

function cerca(actual, esperado, tolerancia = 1e-9) {
  assert.ok(Math.abs(actual - esperado) <= tolerancia, `${actual} != ${esperado}`);
}

// 3 bloques, 40 alumnos, 1 profesor: 3 × 35/60 × 1,40 = 2,45 h.
cerca(model.calcularAsignatura({ bloques: 3, alumnos: 40, profesores: 1 }), 2.45);

// La docencia compartida divide el resultado por el número de profesores.
cerca(model.calcularAsignatura({ bloques: 3, alumnos: 40, profesores: 2 }), 1.225);

// Cada guía equivale a 35 minutos semanales; talleres y diplomado son constantes.
const docencia = model.calcularDocencia({
  asignaturas: [],
  tesistas: 4,
  talleres: 2,
  diplomado: true,
});
cerca(docencia.total, 4 * 35 / 60 + 2 + 2);

// El sitio limita publicaciones a 4 y las bloquea si hay proyecto externo responsable.
assert.equal(model.calcularInvestigacion({ articulos: 9 }).articulos, 16);
assert.equal(model.calcularInvestigacion({ proyectosExternosResponsable: 1, articulos: 4 }).articulos, 0);

// Los dos tipos de jefatura de docencia son mutuamente excluyentes.
assert.equal(model.calcularGestion({ cargos: ["jefeDocenciaConApoyo", "jefeDocenciaSinApoyo"] }).total, 20);

// Escenario mixto para comprobar la suma consolidada.
const total = model.calcularCarga({
  docencia: { asignaturas: [{ bloques: 4, alumnos: 25, profesores: 1 }], tesistas: 2 },
  investigacion: { proyectosCoinvestigador: 1 },
  vinculacion: { asistenciaTecnica: true },
  gestion: { cargos: ["jefeInvestigacion"] },
  otrasActividades: 6,
});
cerca(total.totalOficial, (4 * 35 * 1.25 / 60) + (2 * 35 / 60) + 5 + 2 + 3);
cerca(total.totalConOtras, total.totalOficial + 6);

// Paridad con un escenario ingresado en la calculadora institucional el 10-10-2026.
const paridadWeb = model.calcularCarga({
  docencia: {
    asignaturas: [{ bloques: 3, alumnos: 40, profesores: 1 }],
    tesistas: 4,
    talleres: 2,
    diplomado: true,
  },
  investigacion: {
    proyectosExternosResponsable: 1,
    proyectosCoinvestigador: 2,
    articulos: 4,
    proyectosNoAdjudicados: 1,
  },
  vinculacion: Object.fromEntries(Object.keys(model.PESOS_VINCULACION).map(clave => [clave, true])),
  gestion: { cargos: ["decano", "jefeInvestigacion"] },
});
cerca(paridadWeb.docencia.total, 8.783333333333333);
cerca(paridadWeb.investigacion.total, 27);
cerca(paridadWeb.vinculacion.total, 12.5);
cerca(paridadWeb.gestion.total, 23);
assert.equal(paridadWeb.totalOficial.toFixed(2), "71.28");

console.log("OK: fórmulas verificadas");
