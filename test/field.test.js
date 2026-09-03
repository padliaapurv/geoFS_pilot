'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { createSandbox } = require('./mock.js');

function closeTo(actual, expected, tol, msg) {
  assert.ok(Math.abs(actual - expected) <= tol, `${msg}: expected ${expected} +/- ${tol}, got ${actual}`);
}

function simpleGrid(W) {
  // uMps/vMps/wMps chosen as simple linear-ish functions of index so exact
  // grid-point and midpoint values are easy to predict by hand.
  const xM = [-30, 0, 30];
  const yM = [-10, 0, 10];
  const uMps = [[1, 2, 3], [4, 5, 6], [7, 8, 9]];
  const vMps = [[10, 20, 30], [40, 50, 60], [70, 80, 90]];
  const wMps = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  return W.grid.load({ xM, yM, uMps, vMps, wMps, meander: false });
}

test('grid.load rejects a non-increasing axis', () => {
  const { W } = createSandbox();
  assert.throws(() => W.grid.load({
    xM: [0, 30, 10], yM: [-10, 0, 10],
    uMps: [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
    vMps: [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
    wMps: [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
  }), /increasing/);
});

test('grid.load rejects a mismatched matrix shape', () => {
  const { W } = createSandbox();
  assert.throws(() => W.grid.load({
    xM: [-30, 0, 30], yM: [-10, 0, 10],
    uMps: [[0, 0], [0, 0], [0, 0]], // wrong width
    vMps: [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
    wMps: [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
  }), /matrix layout/);
});

test('grid.load maps vxMps/vyMps to vMps/wMps and defaults uMps to zero', () => {
  const { W } = createSandbox();
  const xM = [-30, 0, 30];
  const yM = [-10, 0, 10];
  const vxMps = [[1, 2, 3], [4, 5, 6], [7, 8, 9]];
  const vyMps = [[9, 8, 7], [6, 5, 4], [3, 2, 1]];
  W.grid.load({ xM, yM, vxMps, vyMps, meander: false });
  const sample = W.sampleWake({ downstreamM: 300, crossM: 0, verticalM: 0 }, 0);
  assert.equal(sample.uMps, 0, 'uMps should default to zero when only vxMps/vyMps are given');
  closeTo(sample.vMps, 5, 1e-9, 'vMps should come from the vxMps grid at the center point');
  closeTo(sample.wMps, 5, 1e-9, 'wMps should come from the vyMps grid at the center point');
});

test('gridSample returns exact grid values at grid points', () => {
  const { W } = createSandbox();
  simpleGrid(W);
  // center grid point (x=0, y=0) -> uMps=5, vMps=50, wMps=0
  const s = W.sampleWake({ downstreamM: 300, crossM: 0, verticalM: 0 }, 0);
  closeTo(s.uMps, 5, 1e-9, 'uMps at grid point');
  closeTo(s.vMps, 50, 1e-9, 'vMps at grid point');
  // top-right grid point (x=30, y=10) -> uMps=9, vMps=90
  const s2 = W.sampleWake({ downstreamM: 300, crossM: 30, verticalM: 10 }, 0);
  closeTo(s2.uMps, 9, 1e-9, 'uMps at top-right grid point');
  closeTo(s2.vMps, 90, 1e-9, 'vMps at top-right grid point');
});

test('gridSample bilinearly interpolates at a cell midpoint', () => {
  const { W } = createSandbox();
  simpleGrid(W);
  // midpoint between (x=-30,y=-10)=1 and (x=0,y=-10)=2 and (x=-30,y=0)=4 and (x=0,y=0)=5
  // at x=-15, y=-5 the bilinear average of {1,2,4,5} is 3
  const s = W.sampleWake({ downstreamM: 300, crossM: -15, verticalM: -5 }, 0);
  closeTo(s.uMps, 3, 1e-9, 'bilinear midpoint of uMps');
  // vMps corners {10,20,40,50} average to 30
  closeTo(s.vMps, 30, 1e-9, 'bilinear midpoint of vMps');
});

test('gridSample clamps sample points outside the grid range to the edge', () => {
  const { W } = createSandbox();
  simpleGrid(W);
  const farRight = W.sampleWake({ downstreamM: 300, crossM: 9999, verticalM: 10 }, 0);
  const edge = W.sampleWake({ downstreamM: 300, crossM: 30, verticalM: 10 }, 0);
  closeTo(farRight.uMps, edge.uMps, 1e-9, 'sampling beyond the grid edge should clamp, not extrapolate');
});

test('gridSample applies downstream decay beyond the reference distance', () => {
  const { W } = createSandbox();
  W.grid.load({
    xM: [-30, 0, 30], yM: [-10, 0, 10],
    uMps: [[10, 10, 10], [10, 10, 10], [10, 10, 10]],
    vMps: [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
    wMps: [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
    meander: false,
    downstreamReferenceM: 300,
    downstreamDecayLengthM: 300,
  });
  const near = W.sampleWake({ downstreamM: 300, crossM: 0, verticalM: 0 }, 0);
  const far = W.sampleWake({ downstreamM: 600, crossM: 0, verticalM: 0 }, 0);
  closeTo(near.uMps, 10, 1e-9, 'no decay at the reference distance');
  closeTo(far.uMps, 10 * Math.exp(-1), 1e-6, 'one decay-length past the reference should attenuate by 1/e');
});

test('gridSample honors inputConvention geofsAirVelocity by negating the input', () => {
  const { W } = createSandbox();
  W.grid.load({
    xM: [-30, 0, 30], yM: [-10, 0, 10],
    uMps: [[5, 5, 5], [5, 5, 5], [5, 5, 5]],
    vMps: [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
    wMps: [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
    meander: false,
    inputConvention: 'geofsAirVelocity',
  });
  const s = W.sampleWake({ downstreamM: 300, crossM: 0, verticalM: 0 }, 0);
  closeTo(s.uMps, -5, 1e-9, 'geofsAirVelocity convention should negate the raw grid value');
});

test('grid.clear falls back to the placeholder wake model', () => {
  const { W } = createSandbox();
  simpleGrid(W);
  W.grid.clear();
  const s = W.sampleWake({ downstreamM: 300, crossM: 0, verticalM: -2.5 }, 0);
  assert.equal(s.source, 'placeholder', 'sampleWake should use the placeholder model once the grid is cleared');
});

// --- placeholder (temporary) wake model ---
test('placeholder model: benefit peaks at 1 at its own reported ideal point', () => {
  const { W } = createSandbox();
  const probe = W.sampleWake({ downstreamM: 300, crossM: 0, verticalM: 0 }, 12.3);
  assert.equal(probe.source, 'placeholder');
  assert.ok(probe.ideal, 'placeholder sample should report an ideal point');
  const atIdeal = W.sampleWake({ downstreamM: 300, crossM: probe.ideal.xM, verticalM: probe.ideal.yM }, 12.3);
  closeTo(atIdeal.scoreTruth, 1, 1e-6, 'benefit (scoreTruth) should be ~1 exactly at the reported ideal point');
  closeTo(atIdeal.uMps, 4.5, 1e-6, 'uMps should be at its documented peak value at the ideal point');
});

test('placeholder model: benefit falls off far from the ideal point', () => {
  const { W } = createSandbox();
  const probe = W.sampleWake({ downstreamM: 300, crossM: 0, verticalM: 0 }, 0);
  const far = W.sampleWake({ downstreamM: 300, crossM: probe.ideal.xM + 500, verticalM: probe.ideal.yM + 500 }, 0);
  assert.ok(far.scoreTruth < 0.01, `benefit should be ~0 far from the ideal point, got ${far.scoreTruth}`);
});

test('placeholder model: outputs stay within documented clamp bounds', () => {
  const { W } = createSandbox();
  for (let d = 80; d <= 2000; d += 137) {
    for (let x = -60; x <= 60; x += 23) {
      for (let y = -30; y <= 30; y += 17) {
        const s = W.sampleWake({ downstreamM: d, crossM: x, verticalM: y }, d * 1.7);
        assert.ok(Number.isFinite(s.uMps) && Number.isFinite(s.vMps) && Number.isFinite(s.wMps), 'wake sample must be finite everywhere');
        assert.ok(s.vMps >= -12 - 1e-9 && s.vMps <= 12 + 1e-9, `vMps out of clamp bounds: ${s.vMps}`);
        assert.ok(s.wMps >= -12 - 1e-9 && s.wMps <= 12 + 1e-9, `wMps out of clamp bounds: ${s.wMps}`);
      }
    }
  }
});

test('grid.example loads without throwing and reports the documented metadata', () => {
  const { W } = createSandbox();
  const meta = W.grid.example();
  assert.equal(meta.nx, 5);
  assert.equal(meta.ny, 5);
  assert.deepEqual({ xM: meta.ideal.xM, yM: meta.ideal.yM }, { xM: 25, yM: 5 });
});
