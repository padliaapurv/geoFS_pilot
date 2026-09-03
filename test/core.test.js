'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { createSandbox } = require('./mock.js');

function closeTo(actual, expected, tol, msg) {
  assert.ok(Math.abs(actual - expected) <= tol, `${msg}: expected ${expected} +/- ${tol}, got ${actual}`);
}

test('wrap360 normalizes into [0, 360)', () => {
  const { W } = createSandbox();
  assert.equal(W.wrap360(0), 0);
  assert.equal(W.wrap360(360), 0);
  assert.equal(W.wrap360(-10), 350);
  assert.equal(W.wrap360(370), 10);
  assert.equal(W.wrap360(720 + 45), 45);
});

test('clamp bounds a value', () => {
  const { W } = createSandbox();
  assert.equal(W.clamp(5, 0, 10), 5);
  assert.equal(W.clamp(-5, 0, 10), 0);
  assert.equal(W.clamp(15, 0, 10), 10);
});

test('isaDensity matches ISA reference points', () => {
  const { W } = createSandbox();
  closeTo(W.isaDensity(0), 1.225, 0.001, 'sea level density');
  closeTo(W.isaDensity(11000), 0.3639, 0.001, 'tropopause density');
  // density strictly decreases with altitude up to the tropopause
  const d0 = W.isaDensity(0);
  const d5000 = W.isaDensity(5000);
  const d10000 = W.isaDensity(10000);
  assert.ok(d0 > d5000 && d5000 > d10000, 'density should decrease monotonically with altitude below 11km');
});

test('trimKias: higher CL requires lower trim speed for the same mass', () => {
  const { W } = createSandbox();
  const massKg = 200000;
  const kias05 = W.trimKias(massKg, 0.5);
  const kias08 = W.trimKias(massKg, 0.8);
  assert.ok(kias08 < kias05, `CL=0.8 (${kias08}kt) should trim slower than CL=0.5 (${kias05}kt)`);
  assert.ok(kias05 > 100 && kias05 < 400, `CL=0.5 trim speed should be a plausible 777 KIAS, got ${kias05}`);
});

test('trimKias: higher mass requires higher trim speed for the same CL', () => {
  const { W } = createSandbox();
  const light = W.trimKias(150000, 0.5);
  const heavy = W.trimKias(250000, 0.5);
  assert.ok(heavy > light, 'heavier aircraft should trim faster at the same CL');
});

test('trimTasMps increases with altitude at fixed CL (constant IAS -> increasing TAS)', () => {
  const { W } = createSandbox();
  const low = W.trimTasMps(200000, 1000, 0.5);
  const high = W.trimTasMps(200000, 10000, 0.5);
  assert.ok(high > low, 'TAS for a fixed CL trim should increase with altitude as air density drops');
});

// --- relativeToLeader / positionBehindLeader round-trip ---
// These two functions must be exact inverses of each other for the
// formation-following math to be self-consistent. Round-trip at several
// headings to catch any sign error that only appears in one quadrant.
test('positionBehindLeader -> relativeToLeader round-trips at heading 0 (north)', () => {
  const { W } = createSandbox();
  const leader = { latDeg: 37.6, lonDeg: -122.3, altitudeM: 3000, headingDeg: 0 };
  for (const [downstreamM, crossM, verticalM] of [[300, 0, 0], [300, 20, -10], [500, -35, 15]]) {
    const followerPos = W.positionBehindLeader(leader, downstreamM, crossM, verticalM);
    const follower = { latDeg: followerPos.latDeg, lonDeg: followerPos.lonDeg, altitudeM: followerPos.altitudeM };
    const rel = W.relativeToLeader(leader, follower);
    closeTo(rel.downstreamM, downstreamM, 0.05, 'downstreamM round-trip at heading 0');
    closeTo(rel.crossM, crossM, 0.05, 'crossM round-trip at heading 0');
    closeTo(rel.verticalM, verticalM, 1e-6, 'verticalM round-trip at heading 0');
  }
});

for (const headingDeg of [0, 45, 90, 135, 180, 225, 270, 315]) {
  test(`positionBehindLeader -> relativeToLeader round-trips at heading ${headingDeg}`, () => {
    const { W } = createSandbox();
    const leader = { latDeg: 10, lonDeg: 20, altitudeM: 3000, headingDeg };
    const downstreamM = 300;
    const crossM = 25;
    const verticalM = -8;
    const followerPos = W.positionBehindLeader(leader, downstreamM, crossM, verticalM);
    const follower = { latDeg: followerPos.latDeg, lonDeg: followerPos.lonDeg, altitudeM: followerPos.altitudeM };
    const rel = W.relativeToLeader(leader, follower);
    closeTo(rel.downstreamM, downstreamM, 0.05, `downstreamM round-trip at heading ${headingDeg}`);
    closeTo(rel.crossM, crossM, 0.05, `crossM round-trip at heading ${headingDeg}`);
  });
}

test('positionBehindLeader places the follower directly behind on the correct side', () => {
  const { W } = createSandbox();
  // Leader heading due north (0deg). A point 300m downstream (behind) and
  // 50m to the right (cross) should end up south and east of the leader.
  const leader = { latDeg: 0, lonDeg: 0, altitudeM: 0, headingDeg: 0 };
  const p = W.positionBehindLeader(leader, 300, 50, 0);
  assert.ok(p.latDeg < leader.latDeg, 'behind a north-heading leader should be south (lower latitude)');
  assert.ok(p.lonDeg > leader.lonDeg, 'right of a north-heading leader should be east (higher longitude)');
});

test('relativeToLeader: a follower due east of a north-heading leader is entirely cross, not downstream', () => {
  const { W } = createSandbox();
  const leader = { latDeg: 0, lonDeg: 0, altitudeM: 0, headingDeg: 0 };
  // ~1000m east at the equator
  const follower = { latDeg: 0, lonDeg: 1000 / (Math.PI / 180 * 6371000), altitudeM: 0 };
  const rel = W.relativeToLeader(leader, follower);
  closeTo(rel.downstreamM, 0, 1, 'due-east offset should have ~zero downstream component for a north-heading leader');
  assert.ok(rel.crossM > 900, `due-east offset should read as strongly positive cross, got ${rel.crossM}`);
});

// --- injectWakeWind sign convention ---
test('injectWakeWind: a pure forward (tailwind-from-behind) wake at heading 0 shows up as a southward wind vector', () => {
  const { W, sandbox } = createSandbox();
  // heading 0 (north), pure forward air-mass velocity (u=10, v=0, w=0):
  // physical air is moving north at 10 m/s under the aircraft.
  W.injectWakeWind({ uMps: 10, vMps: 0, wMps: 0 }, 0, true);
  const vec = sandbox.weather.currentWindVector;
  // vec = base - airMassVelocity(ENU); airMass here is (east=0, north=10, up=0)
  closeTo(vec[0], 0, 1e-6, 'east component');
  closeTo(vec[1], -10, 1e-6, 'north component should be negative of the northward air-mass velocity');
  closeTo(vec[2], 0, 1e-6, 'up component');
});

test('injectWakeWind: cross (rightward) wake at heading 90 (east) maps to a southward air-mass component', () => {
  const { W, sandbox } = createSandbox();
  // heading 90 (east-facing leader): "right" of the aircraft is south.
  W.injectWakeWind({ uMps: 0, vMps: 10, wMps: 0 }, 90, true);
  const vec = sandbox.weather.currentWindVector;
  // airMass east = u*sin(90)+v*cos(90) = 0; airMass north = u*cos(90)-v*sin(90) = -10
  // so physical air-mass velocity is (0, -10) i.e. blowing south, and injected vec = -airMass
  closeTo(vec[0], 0, 1e-6, 'east component');
  closeTo(vec[1], 10, 1e-6, 'north component');
});

test('injectWakeWind: zeroAmbientWind=false adds on top of the original wind instead of replacing it', () => {
  const { W, sandbox } = createSandbox();
  sandbox.GeoFSWake.state.originalWind = [5, 5, 0];
  W.injectWakeWind({ uMps: 0, vMps: 0, wMps: 0 }, 0, false);
  // Array.from() strips the sandbox's cross-realm Array identity so
  // assert.deepEqual compares values, not prototype/realm.
  assert.deepEqual(Array.from(sandbox.weather.currentWindVector), [5, 5, 0], 'zero wake vector with ambient wind kept should just be the ambient wind');
});

test('aircraftMassKg falls back to the documented default when nothing plausible is available', () => {
  const { W, sandbox } = createSandbox();
  sandbox.geofs.aircraft.instance.rigidBody = {};
  delete sandbox.geofs.aircraft.instance.definition.mass;
  const m = W.aircraftMassKg(undefined);
  assert.equal(m, W.constants.aircraft.fallbackMassKg);
});

test('aircraftMassKg prefers an explicit override over the aircraft-reported mass', () => {
  const { W } = createSandbox();
  assert.equal(W.aircraftMassKg(180000), 180000);
});

// --- setThrottle / startEngines ---
test('setThrottle clamps to [0, 1] and writes controls.throttle directly', () => {
  const { W, sandbox } = createSandbox();
  W.setThrottle(0.85);
  assert.equal(sandbox.controls.throttle, 0.85);
  W.setThrottle(1.5);
  assert.equal(sandbox.controls.throttle, 1);
  W.setThrottle(-0.2);
  assert.equal(sandbox.controls.throttle, 0);
});

test('startEngines turns the engine on', () => {
  const { W, sandbox } = createSandbox();
  assert.equal(sandbox.controls.engine.on, false);
  W.startEngines();
  assert.equal(sandbox.controls.engine.on, true);
});

test('commandTrim starts the engines when they are off', async () => {
  const { W, sandbox } = createSandbox();
  await W.commandTrim({ cl: 0.5, altitudeFt: 10000, reposition: false });
  assert.equal(sandbox.controls.engine.on, true);
});

test('commandTrim honors an explicit throttle override', async () => {
  const { W, sandbox } = createSandbox();
  sandbox.controls.throttle = 0.7;
  await W.commandTrim({ cl: 0.5, altitudeFt: 10000, reposition: false, throttle: 0.95 });
  assert.equal(sandbox.controls.throttle, 0.95);
});

// --- commandTrim / autopilot engage ordering ---
// Found via live testing against real GeoFS: geofs.autopilot.turnOn() itself
// re-captures the CURRENT heading/altitude/speed as its bugs, clobbering
// anything set beforehand. commandTrim must call enableAutopilot() BEFORE
// setAutopilotTargets(), not after, or the trim target is silently replaced
// by whatever the aircraft happened to be doing at the moment it engaged.
test('commandTrim sets autopilot targets that survive turnOn\'s current-state capture', async () => {
  const { W, sandbox } = createSandbox();
  // Mock's "current" flight state (heading 90, altitude 10000ft, kias 250)
  // deliberately differs from the requested trim target below, so a
  // regression to the old (setTargets-then-turnOn) order would leave the
  // bugs at the current state instead of the requested target.
  const trim = await W.commandTrim({ cl: 0.5, massKg: 200000, altitudeFt: 15000, headingDeg: 270, reposition: false });
  const ap = sandbox.geofs.autopilot;
  assert.equal(ap.values.altitude, 15000);
  assert.equal(ap.values.course, 270);
  closeTo(ap.values.speed, trim.speedKias, 1e-6, 'autopilot speed bug should be the trim target, not the pre-engage current speed');
  assert.notEqual(ap.values.speed, 250, 'must not be left at the mock\'s pre-engage current kias');
});

// --- placeAircraft velocity ---
// Found via live testing against real GeoFS: aircraft.instance.place(lla,
// htr) only sets position/orientation. It never touched velocity, so a
// teleported aircraft kept whatever velocity it had before (usually ~0) and
// fell out of the sky in true free fall until the autopilot fought it back
// under control (if it could at all). The real physics velocity lives at
// rigidBody.v_linearVelocity, a plain [east, north, up] m/s vector in the
// same ENU frame injectWakeWind already uses.
test('placeAircraft sets rigidBody.v_linearVelocity from heading and speed, not just position', () => {
  const { W, sandbox } = createSandbox();
  const ok = W.placeAircraft({ latDeg: 10, lonDeg: 20, altitudeM: 3000, headingDeg: 90 }, 200);
  assert.equal(ok, true);
  const v = sandbox.geofs.aircraft.instance.rigidBody.v_linearVelocity;
  closeTo(v[0], 200, 1e-6, 'east component at heading 90 (due east) should be the full speed');
  closeTo(v[1], 0, 1e-6, 'north component at heading 90 should be ~zero');
  closeTo(v[2], 0, 1e-6, 'level placement should have zero vertical velocity');
});

test('placeAircraft leaves velocity untouched when no speed is given', () => {
  const { W, sandbox } = createSandbox();
  sandbox.geofs.aircraft.instance.rigidBody.v_linearVelocity = [11, 22, 33];
  W.placeAircraft({ latDeg: 10, lonDeg: 20, altitudeM: 3000, headingDeg: 90 }, undefined);
  assert.deepEqual(Array.from(sandbox.geofs.aircraft.instance.rigidBody.v_linearVelocity), [11, 22, 33]);
});
