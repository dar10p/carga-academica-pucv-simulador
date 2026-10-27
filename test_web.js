"use strict";
// Comprueba que real.js y la réplica oficial (model.js) dan las mismas cifras que el
// simulador en Python (fixtures.json, generado por simulador/generar.py).
const assert = require("node:assert/strict");
const P = require("./parametros.js");
const oficial = require("./model.js");
const real = require("./real.js");
const { perfiles, casos } = require("./fixtures.json");

function aOficial(datos) {
  const d = JSON.parse(JSON.stringify(datos));
  const t = d.docencia?.tesistas;
  if (t && typeof t === "object") d.docencia.tesistas = Object.values(t).reduce((a, b) => a + b, 0);
  if (d.investigacion) d.investigacion.articulos = (d.investigacion.articulos || 0) + (d.investigacion.articulosBajaExigencia || 0);
  if (d.vinculacion) for (const k of Object.keys(d.vinculacion)) d.vinculacion[k] = Number(d.vinculacion[k]) > 0 || d.vinculacion[k] === true;
  return d;
}

const porId = Object.fromEntries(perfiles.map(p => [p.id, p.datos]));
let n = 0;
for (const c of casos) {
  const datos = porId[c.perfil];
  const cred = oficial.calcularCarga(aOficial(datos)).totalOficial;
  assert.ok(Math.abs(cred - c.credito) < 1e-9, `${c.perfil}: crédito ${cred} != ${c.credito}`);
  const r = real.horasReales(datos, real.resolver(P, c.nivel), c.modo);
  for (const k of Object.keys(c.real)) {
    assert.ok(Math.abs(r[k] - c.real[k]) < 1e-9, `${c.perfil}/${c.modo}/${c.nivel}/${k}: ${r[k]} != ${c.real[k]}`);
  }
  n++;
}
console.log(`OK: ${n} casos idénticos entre Python y JavaScript`);
