'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { createSandbox } = require('./mock.js');

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

test('guidance.setMode rejects unknown modes and accepts documented ones', () => {
  const { W } = createSandbox();
  assert.throws(() => W.guidance.setMode('bogus'), /mode must be/);
  for (const mode of ['hold', 'truth', 'seek']) {
    assert.equal(W.guidance.setMode(mode), mode);
    assert.equal(W.state.guidanceMode, mode);
  }
});

test('guidance.hold throws if the follower has not started', () => {
  const { W } = createSandbox();
  assert.throws(() => W.guidance.hold(10, 5), /Follower is not running/);
});

test('status() reports idle role and no aircraft data before anything starts', () => {
  const { W } = createSandbox({ geofs: { aircraft: false } });
  const s = W.status();
  assert.equal(s.role, 'idle');
  assert.equal(s.aircraft, null);
});

test('data.history/csv start empty and data.clear empties an existing history', () => {
  const { W } = createSandbox();
  assert.deepEqual(Array.from(W.data.history()), []);
  W.state.history.push({
    timeSec: 1, mode: 'hold', relative: { downstreamM: 300, crossM: 0, verticalM: 0 },
    target: { xM: 0, yM: 0 }, ideal: null,
    wake: { uMps: 1, vMps: 2, wMps: 3, scoreTruth: null, source: 'placeholder' },
    flight: { kias: 250, tasKt: 260, altitudeFt: 10000, verticalSpeedFpm: 0 }, seeker: null,
  });
  const csv = W.data.csv();
  const lines = csv.split('\n');
  assert.equal(lines.length, 2, 'header + one data row');
  assert.match(lines[0], /^timeSec,mode,downstreamM/);
  assert.match(lines[1], /^1,hold,300,0,0/);
  W.data.clear();
  assert.deepEqual(Array.from(W.data.history()), []);
});

test('startLeader publishes periodic leader-state broadcasts that a follower on the same session receives', async () => {
  const leader = createSandbox();
  const follower = createSandbox();
  try {
    await leader.W.startLeader({ session: 'test-session-a', cl: 0.5, altitudeFt: 10000, headingDeg: 90, publishPeriodMs: 30 });
    assert.equal(leader.W.state.role, 'leader');
    assert.equal(leader.W.state.trim.cl, 0.5);

    // Listen on a bare BroadcastChannel with the same name/session to avoid
    // depending on follower.W's internal wiring for this first assertion.
    const probe = new BroadcastChannel('geofs-wake-test-session-a');
    const received = await new Promise((resolve) => {
      probe.onmessage = (e) => resolve(e.data);
    });
    probe.close();
    assert.equal(received.type, 'leader-state');
    assert.equal(received.session, 'test-session-a');
    assert.equal(received.state.headingDeg, 90);
  } finally {
    leader.W.stop();
    follower.W.stop();
  }
});

test('startFollower rejects when no leader publishes on the session within the timeout', async () => {
  const { W } = createSandbox();
  await assert.rejects(
    W.startFollower({ session: 'test-session-lonely', leaderTimeoutMs: 200, reposition: false }),
    /No fresh leader telemetry/
  );
  W.stop();
});

test('full leader->follower loop: follower receives leader state, samples wake, and injects wind', async () => {
  const leader = createSandbox();
  const follower = createSandbox();
  try {
    await leader.W.startLeader({ session: 'test-session-b', cl: 0.5, altitudeFt: 10000, headingDeg: 0, publishPeriodMs: 30 });
    await sleep(60); // let at least one leader-state broadcast land

    await follower.W.startFollower({
      session: 'test-session-b',
      mode: 'hold',
      targetDownstreamM: 300,
      initialCrossM: 5,
      initialVerticalM: -2,
      reposition: false,
      wakePeriodMs: 30,
      controlPeriodMs: 50,
    });

    await sleep(150); // let a few wake/control ticks run

    assert.equal(follower.W.state.role, 'follower');
    assert.ok(follower.W.state.leader, 'follower should have received leader telemetry');
    assert.ok(follower.W.state.lastWake, 'follower should have sampled the wake at least once');
    assert.ok(follower.W.state.lastRelative, 'follower should have computed a relative position');
    assert.equal(follower.W.state.lastWake.source, 'placeholder', 'no grid loaded, should use the placeholder model');

    const vec = follower.sandbox.weather.currentWindVector;
    assert.ok(Number.isFinite(vec[0]) && Number.isFinite(vec[1]) && Number.isFinite(vec[2]), 'injected wind vector must be finite');

    assert.ok(follower.W.state.history.length > 0, 'controlStep should have recorded at least one history entry');
    const entry = follower.W.state.history[follower.W.state.history.length - 1];
    assert.equal(entry.mode, 'hold');
    assert.equal(entry.target.xM, 5, 'hold mode should command the configured holdCrossM (== initialCrossM here)');
    assert.equal(entry.target.yM, -2, 'hold mode should command the configured holdVerticalM (== initialVerticalM here)');
  } finally {
    leader.W.stop();
    follower.W.stop();
  }
});

test('guidance.hold updates the follower target and switches mode to hold mid-run', async () => {
  const leader = createSandbox();
  const follower = createSandbox();
  try {
    await leader.W.startLeader({ session: 'test-session-c', publishPeriodMs: 30 });
    await sleep(60);
    await follower.W.startFollower({
      session: 'test-session-c', mode: 'seek', reposition: false,
      wakePeriodMs: 30, controlPeriodMs: 50,
    });
    await sleep(60);

    follower.W.guidance.hold(15, -6);
    assert.equal(follower.W.state.guidanceMode, 'hold');
    await sleep(80);

    const entry = follower.W.state.history[follower.W.state.history.length - 1];
    assert.equal(entry.mode, 'hold');
    assert.equal(entry.target.xM, 15);
    assert.equal(entry.target.yM, -6);
  } finally {
    leader.W.stop();
    follower.W.stop();
  }
});

test('stop() restores the original weather.update and wind vector and clears role/timers', async () => {
  const leader = createSandbox();
  const follower = createSandbox();
  try {
    const originalUpdate = follower.sandbox.weather.update;
    follower.sandbox.weather.currentWindVector = [1, 2, 3];

    await leader.W.startLeader({ session: 'test-session-d', publishPeriodMs: 30 });
    await sleep(60);
    await follower.W.startFollower({ session: 'test-session-d', mode: 'hold', reposition: false, wakePeriodMs: 30, controlPeriodMs: 50 });
    await sleep(60);

    assert.notEqual(follower.sandbox.weather.update, originalUpdate, 'installWeatherHook should have wrapped weather.update');

    follower.W.stop();
    assert.equal(follower.W.state.role, 'idle');
    assert.equal(follower.sandbox.weather.update, originalUpdate, 'stop() should restore the original weather.update');
    assert.equal(follower.W.state.timers.length, 0, 'stop() should clear all timers');
  } finally {
    leader.W.stop();
    follower.W.stop();
  }
});

test('truth mode commands the wake model ideal point, not the seeker', async () => {
  const leader = createSandbox();
  const follower = createSandbox();
  try {
    await leader.W.startLeader({ session: 'test-session-e', publishPeriodMs: 30 });
    await sleep(60);
    await follower.W.startFollower({
      session: 'test-session-e', mode: 'truth', reposition: false,
      wakePeriodMs: 30, controlPeriodMs: 50,
    });
    await sleep(120);

    const entry = follower.W.state.history[follower.W.state.history.length - 1];
    assert.ok(entry.ideal, 'placeholder model should report an ideal point in truth mode');
    assert.equal(entry.target.xM, entry.ideal.xM, 'truth mode should command exactly the ideal xM');
    assert.equal(entry.target.yM, entry.ideal.yM, 'truth mode should command exactly the ideal yM');
  } finally {
    leader.W.stop();
    follower.W.stop();
  }
});
