'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { createSandbox } = require('./mock.js');

function runSeekerAgainstPeak(W, { x0, y0, sigma = 15, iterations = 4000, dt = 0.25, seekerOptions = {} }) {
  const seeker = W.newSeeker({ warmupSec: 5, ...seekerOptions });
  // newSeeker stamps startedSec from performance.now(); walk simulated time
  // forward manually so the test runs instantly instead of over real wall time.
  let t = seeker.startedSec;
  const objectiveAt = (x, y) => Math.exp(-((x - x0) ** 2 + (y - y0) ** 2) / (2 * sigma * sigma));
  for (let i = 0; i < iterations; i++) {
    t += dt;
    const objective = objectiveAt(seeker.commandX, seeker.commandY);
    W.updateSeeker(seeker, t, objective);
  }
  return seeker;
}

test('newSeeker applies documented defaults and options overrides', () => {
  const { W } = createSandbox();
  const s = W.newSeeker({});
  assert.equal(s.amplitudeX, 7);
  assert.equal(s.amplitudeY, 4);
  assert.equal(s.centerX, 0);
  assert.equal(s.centerY, 0);
  const s2 = W.newSeeker({ initialCrossM: 12, initialVerticalM: -3, amplitudeCrossM: 1, gainCross: 9 });
  assert.equal(s2.centerX, 12);
  assert.equal(s2.centerY, -3);
  assert.equal(s2.amplitudeX, 1);
  assert.equal(s2.gainX, 9);
});

test('updateSeeker returns the last command unchanged for a non-finite objective', () => {
  const { W } = createSandbox();
  const s = W.newSeeker({});
  const before = { x: s.commandX, y: s.commandY };
  const out = W.updateSeeker(s, s.startedSec + 1, NaN);
  assert.equal(out.xM, before.x);
  assert.equal(out.yM, before.y);
});

test('updateSeeker does not move the dither center before warmup elapses', () => {
  const { W } = createSandbox();
  const s = W.newSeeker({ warmupSec: 1000 });
  for (let i = 1; i <= 50; i++) {
    W.updateSeeker(s, s.startedSec + i * 0.5, 1); // constant objective, no gradient info anyway
  }
  assert.equal(s.centerX, 0, 'center should not move before warmupSec has elapsed');
  assert.equal(s.centerY, 0, 'center should not move before warmupSec has elapsed');
});

test('updateSeeker climbs toward a stationary objective peak (extremum seeking works)', () => {
  const { W } = createSandbox();
  const seeker = runSeekerAgainstPeak(W, { x0: 20, y0: -8 });
  const distStart = Math.hypot(0 - 20, 0 - (-8));
  const distEnd = Math.hypot(seeker.centerX - 20, seeker.centerY - (-8));
  assert.ok(distEnd < distStart * 0.35, `seeker should converge substantially toward the peak: start dist ${distStart.toFixed(1)}m, end dist ${distEnd.toFixed(1)}m (center ${seeker.centerX.toFixed(1)}, ${seeker.centerY.toFixed(1)})`);
});

test('updateSeeker converges from the opposite quadrant too (not direction-dependent)', () => {
  const { W } = createSandbox();
  const seeker = runSeekerAgainstPeak(W, { x0: -30, y0: 15 });
  const distEnd = Math.hypot(seeker.centerX - (-30), seeker.centerY - 15);
  assert.ok(distEnd < 20, `seeker should approach a peak in the opposite quadrant, ended ${distEnd.toFixed(1)}m away at (${seeker.centerX.toFixed(1)}, ${seeker.centerY.toFixed(1)})`);
});

test('updateSeeker respects min/max bounds even when the peak is outside them', () => {
  const { W } = createSandbox();
  const seeker = runSeekerAgainstPeak(W, {
    x0: 500, y0: 500, iterations: 3000,
    seekerOptions: { minCrossM: -20, maxCrossM: 20, minVerticalM: -10, maxVerticalM: 10 },
  });
  assert.ok(seeker.centerX <= 20 + 1e-9 && seeker.centerX >= -20 - 1e-9, `centerX ${seeker.centerX} exceeded bounds`);
  assert.ok(seeker.centerY <= 10 + 1e-9 && seeker.centerY >= -10 - 1e-9, `centerY ${seeker.centerY} exceeded bounds`);
  assert.ok(seeker.commandX <= 20 + 1e-9 && seeker.commandX >= -20 - 1e-9, `commandX ${seeker.commandX} exceeded bounds`);
});

test('updateSeeker treats a flat (uninformative) objective as no gradient: center stays near start', () => {
  const { W } = createSandbox();
  const seeker = W.newSeeker({ warmupSec: 2 });
  let t = seeker.startedSec;
  for (let i = 0; i < 2000; i++) {
    t += 0.25;
    W.updateSeeker(seeker, t, 0.5); // perfectly flat objective everywhere
  }
  assert.ok(Math.abs(seeker.centerX) < 1, `flat objective should not produce a spurious gradient, drifted to centerX=${seeker.centerX}`);
  assert.ok(Math.abs(seeker.centerY) < 1, `flat objective should not produce a spurious gradient, drifted to centerY=${seeker.centerY}`);
});

test('W.measuredObjective rewards lower throttle and penalizes altitude/vs/roll deviation', () => {
  const { W } = createSandbox();
  const base = { throttle: 0.6, altitudeFt: 10000, verticalSpeedFpm: 0, rollDeg: 0 };
  const lowerThrottle = { ...base, throttle: 0.4 };
  assert.ok(W.measuredObjective(lowerThrottle, 10000) > W.measuredObjective(base, 10000), 'lower throttle at the same trim should score higher');

  const offAltitude = { ...base, altitudeFt: 10500 };
  assert.ok(W.measuredObjective(offAltitude, 10000) < W.measuredObjective(base, 10000), 'altitude deviation should be penalized');

  const rolling = { ...base, rollDeg: 20 };
  assert.ok(W.measuredObjective(rolling, 10000) < W.measuredObjective(base, 10000), 'roll should be penalized');
});
