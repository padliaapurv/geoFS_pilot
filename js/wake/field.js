(function () {
  'use strict';

  const W = window.GeoFSWake;
  if (!W) throw new Error('GeoFSWake core must load before field.js');

  function isAxis(a) {
    return Array.isArray(a) && a.length >= 2 && a.every(Number.isFinite) && a.every((v, i) => i === 0 || v > a[i - 1]);
  }

  function isMatrix(m, ny, nx) {
    return Array.isArray(m) && m.length === ny && m.every((r) => Array.isArray(r) && r.length === nx && r.every(Number.isFinite));
  }

  function locate(axis, value) {
    if (value <= axis[0]) return { i0: 0, i1: 1, t: 0 };
    const n = axis.length;
    if (value >= axis[n - 1]) return { i0: n - 2, i1: n - 1, t: 1 };
    let lo = 0;
    let hi = n - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (axis[mid] <= value) lo = mid;
      else hi = mid;
    }
    return { i0: lo, i1: hi, t: (value - axis[lo]) / (axis[hi] - axis[lo]) };
  }

  function bilinear(matrix, lx, ly) {
    const q00 = matrix[ly.i0][lx.i0];
    const q10 = matrix[ly.i0][lx.i1];
    const q01 = matrix[ly.i1][lx.i0];
    const q11 = matrix[ly.i1][lx.i1];
    const a = q00 + lx.t * (q10 - q00);
    const b = q01 + lx.t * (q11 - q01);
    return a + ly.t * (b - a);
  }

  function normalizeGrid(def) {
    const xM = def?.xM;
    const yM = def?.yM;
    if (!isAxis(xM) || !isAxis(yM)) throw new Error('Grid xM and yM must be increasing numeric arrays with at least two points.');
    const nx = xM.length;
    const ny = yM.length;

    let uMps = def.uMps;
    let vMps = def.vMps;
    let wMps = def.wMps;
    if (!vMps && def.vxMps) vMps = def.vxMps;
    if (!wMps && def.vyMps) wMps = def.vyMps;
    if (!uMps) uMps = Array.from({ length: ny }, () => Array(nx).fill(0));

    if (!isMatrix(uMps, ny, nx) || !isMatrix(vMps, ny, nx) || !isMatrix(wMps, ny, nx)) {
      throw new Error('uMps, vMps, and wMps must use matrix layout [yIndex][xIndex]. vxMps/vyMps can replace vMps/wMps.');
    }

    const ideal = def.ideal && Number.isFinite(def.ideal.xM) && Number.isFinite(def.ideal.yM)
      ? { xM: Number(def.ideal.xM), yM: Number(def.ideal.yM) }
      : null;

    return {
      xM: xM.slice(),
      yM: yM.slice(),
      uMps: uMps.map((r) => r.slice()),
      vMps: vMps.map((r) => r.slice()),
      wMps: wMps.map((r) => r.slice()),
      ideal,
      inputConvention: def.inputConvention || 'airMassVelocity',
      downstreamReferenceM: Number.isFinite(def.downstreamReferenceM) ? def.downstreamReferenceM : 300,
      downstreamDecayLengthM: Number.isFinite(def.downstreamDecayLengthM) ? def.downstreamDecayLengthM : Infinity,
      meander: def.meander !== false,
    };
  }

  W.grid = W.grid || {};
  W.grid.load = function (def) {
    const g = normalizeGrid(def);
    W.state.grid = g;
    W.state.gridMeta = {
      nx: g.xM.length,
      ny: g.yM.length,
      xRangeM: [g.xM[0], g.xM[g.xM.length - 1]],
      yRangeM: [g.yM[0], g.yM[g.yM.length - 1]],
      ideal: g.ideal,
      inputConvention: g.inputConvention,
    };
    console.log('[geofsWake] grid loaded', W.state.gridMeta);
    return W.state.gridMeta;
  };

  W.grid.clear = function () {
    W.state.grid = null;
    W.state.gridMeta = null;
  };

  function meander(timeSec, downstreamM) {
    const d = Math.max(50, downstreamM || 300);
    const scale = Math.sqrt(W.clamp(d / 300, 0.5, 4));
    return {
      xM: scale * (7.5 * Math.sin(2 * Math.PI * timeSec / 53) + 2.5 * Math.sin(2 * Math.PI * timeSec / 19)),
      yM: -2.2 * scale + 3.0 * Math.sin(2 * Math.PI * timeSec / 71 + 0.8),
    };
  }

  function gridSample(relative, timeSec) {
    const g = W.state.grid;
    const m = g.meander ? meander(timeSec, relative.downstreamM) : { xM: 0, yM: 0 };
    const x = relative.crossM - m.xM;
    const y = relative.verticalM - m.yM;
    const lx = locate(g.xM, x);
    const ly = locate(g.yM, y);
    const decay = Number.isFinite(g.downstreamDecayLengthM)
      ? Math.exp(-Math.max(0, relative.downstreamM - g.downstreamReferenceM) / g.downstreamDecayLengthM)
      : 1;
    let u = bilinear(g.uMps, lx, ly) * decay;
    let v = bilinear(g.vMps, lx, ly) * decay;
    let w = bilinear(g.wMps, lx, ly) * decay;
    if (g.inputConvention === 'geofsAirVelocity') {
      u = -u;
      v = -v;
      w = -w;
    }
    return {
      uMps: u,
      vMps: v,
      wMps: w,
      scoreTruth: null,
      ideal: g.ideal ? { xM: g.ideal.xM + m.xM, yM: g.ideal.yM + m.yM } : null,
      meander: m,
      source: 'grid',
      sampleXY: { xM: x, yM: y },
    };
  }

  function vortexVelocity(x, y, xc, yc, gamma, coreM, sign) {
    const dx = x - xc;
    const dy = y - yc;
    const r2 = dx * dx + dy * dy + coreM * coreM;
    const k = sign * gamma / (2 * Math.PI * r2);
    return { v: -k * dy, w: k * dx };
  }

  function placeholderSample(relative, timeSec) {
    const d = Math.max(80, relative.downstreamM || 300);
    const m = meander(timeSec, d);
    const x = relative.crossM - m.xM;
    const y = relative.verticalM - m.yM;
    const halfSep = 24;
    const descent = -2.5 * Math.sqrt(W.clamp(d / 300, 0.4, 4));
    const gamma = 240 * Math.exp(-d / 2200);
    const coreM = 5 + 0.006 * d;
    const left = vortexVelocity(x, y, -halfSep, descent, gamma, coreM, 1);
    const right = vortexVelocity(x, y, halfSep, descent, gamma, coreM, -1);

    const idealLocal = { xM: 32, yM: descent + 5 };
    const dx = x - idealLocal.xM;
    const dy = y - idealLocal.yM;
    const sigmaX = 15;
    const sigmaY = 10;
    const benefit = Math.exp(-0.5 * (dx * dx / (sigmaX * sigmaX) + dy * dy / (sigmaY * sigmaY)));

    return {
      uMps: 4.5 * benefit,
      vMps: W.clamp(left.v + right.v, -12, 12),
      wMps: W.clamp(left.w + right.w + 2.0 * benefit, -12, 12),
      scoreTruth: benefit,
      ideal: { xM: idealLocal.xM + m.xM, yM: idealLocal.yM + m.yM },
      meander: m,
      source: 'placeholder',
      sampleXY: { xM: x, yM: y },
    };
  }

  W.sampleWake = function (relative, timeSec) {
    return W.state.grid ? gridSample(relative, timeSec) : placeholderSample(relative, timeSec);
  };

  W.wake = W.wake || {};
  W.wake.ideal = function (relative, timeSec) {
    return W.sampleWake(relative, timeSec).ideal;
  };

  W.grid.example = function () {
    const xM = [-60, -30, 0, 30, 60];
    const yM = [-30, -15, 0, 15, 30];
    const field = (fn) => yM.map((y) => xM.map((x) => fn(x, y)));
    return W.grid.load({
      xM,
      yM,
      uMps: field((x, y) => 5 * Math.exp(-((x - 25) ** 2 + (y - 5) ** 2) / 500)),
      vMps: field((x, y) => -0.02 * y),
      wMps: field((x, y) => 0.025 * (x - 10)),
      ideal: { xM: 25, yM: 5 },
    });
  };
})();