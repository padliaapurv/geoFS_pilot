(function () {
  'use strict';

  const W = window.GeoFSWake;
  if (!W) throw new Error('GeoFSWake core must load before runtime.js');

  function addTimer(fn, ms) {
    const id = window.setInterval(fn, ms);
    W.state.timers.push(id);
    return id;
  }

  function clearTimers() {
    for (const id of W.state.timers) window.clearInterval(id);
    W.state.timers.length = 0;
  }

  function openChannel(session) {
    if (W.state.channel) W.state.channel.close();
    W.state.session = session || 'b777-wake';
    W.state.channel = new BroadcastChannel(`geofs-wake-${W.state.session}`);
    W.state.channel.onmessage = (event) => {
      const m = event.data;
      if (!m || m.session !== W.state.session) return;
      if (m.type === 'leader-state') W.state.leader = m.state;
    };
    return W.state.channel;
  }

  function publishLeader() {
    if (!W.state.channel || W.state.role !== 'leader') return;
    const f = W.flightState();
    W.state.leader = f;
    W.state.channel.postMessage({
      type: 'leader-state',
      session: W.state.session,
      state: f,
    });
  }

  async function waitForFreshLeader(timeoutMs = 10000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const leader = W.state.leader;
      if (leader && Date.now() - leader.timeMs < 1500) return leader;
      await new Promise((r) => window.setTimeout(r, 100));
    }
    throw new Error('No fresh leader telemetry. Start geofsWake.startLeader() in the other GeoFS tab with the same session.');
  }

  function guidanceTarget(wake, timeSec) {
    const cfg = W.state.follower;
    if (W.state.guidanceMode === 'truth') {
      return wake.ideal || { xM: cfg.holdCrossM, yM: cfg.holdVerticalM };
    }
    if (W.state.guidanceMode === 'hold') {
      return { xM: cfg.holdCrossM, yM: cfg.holdVerticalM };
    }
    const f = W.flightState();
    const altitudeTargetFt = W.state.leader.altitudeFt + (W.state.seeker?.commandY || 0) / W.constants.FT_TO_M;
    const objective = W.measuredObjective(f, altitudeTargetFt);
    return W.updateSeeker(W.state.seeker, timeSec, objective);
  }

  function applyFormationGuidance(target) {
    const cfg = W.state.follower;
    const rel = W.state.lastRelative;
    const leader = W.state.leader;
    const trim = W.state.trim;
    if (!cfg || !rel || !leader || !trim) return;

    const downstreamErrorM = rel.downstreamM - cfg.targetDownstreamM;
    const crossErrorM = rel.crossM - target.xM;
    const speedKias = W.clamp(
      trim.speedKias + cfg.downstreamSpeedGainKtPerM * downstreamErrorM,
      trim.speedKias - cfg.maxSpeedCorrectionKt,
      trim.speedKias + cfg.maxSpeedCorrectionKt
    );
    const headingDeg = W.wrap360(
      leader.headingDeg - W.clamp(cfg.crossHeadingGainDegPerM * crossErrorM, -cfg.maxHeadingCorrectionDeg, cfg.maxHeadingCorrectionDeg)
    );
    const altitudeFt = leader.altitudeFt + target.yM / W.constants.FT_TO_M;

    W.setAutopilotTargets({ headingDeg, altitudeFt, speedKias });
    W.state.lastControl = {
      timeMs: Date.now(),
      target,
      downstreamErrorM,
      crossErrorM,
      headingDeg,
      altitudeFt,
      speedKias,
    };
  }

  function wakePhysicsStep() {
    if (W.state.role !== 'follower' || !W.state.leader) return;
    const f = W.flightState();
    if (f.latDeg == null || f.lonDeg == null) return;
    const rel = W.relativeToLeader(W.state.leader, f);
    const timeSec = (performance.now() - W.state.startedAtMs) / 1000;
    const wake = W.sampleWake(rel, timeSec);
    W.state.lastRelative = rel;
    W.state.lastWake = wake;
    W.injectWakeWind(wake, W.state.leader.headingDeg, W.state.follower.zeroAmbientWind);
  }

  function controlStep() {
    if (W.state.role !== 'follower' || !W.state.leader || !W.state.lastWake || !W.state.lastRelative) return;
    if (Date.now() - W.state.leader.timeMs > 2000) {
      console.warn('[geofsWake] Leader telemetry is stale. Holding last commands.');
      return;
    }
    const timeSec = performance.now() / 1000;
    const target = guidanceTarget(W.state.lastWake, timeSec);
    applyFormationGuidance(target);

    const flight = W.flightState();
    const entry = {
      timeSec: (performance.now() - W.state.startedAtMs) / 1000,
      mode: W.state.guidanceMode,
      relative: { ...W.state.lastRelative },
      target: { ...target },
      ideal: W.state.lastWake.ideal ? { ...W.state.lastWake.ideal } : null,
      wake: {
        uMps: W.state.lastWake.uMps,
        vMps: W.state.lastWake.vMps,
        wMps: W.state.lastWake.wMps,
        scoreTruth: W.state.lastWake.scoreTruth,
        source: W.state.lastWake.source,
      },
      flight: {
        kias: flight.kias,
        tasKt: flight.tasKt,
        altitudeFt: flight.altitudeFt,
        verticalSpeedFpm: flight.verticalSpeedFpm,
        rollDeg: flight.rollDeg,
        pitchDeg: flight.pitchDeg,
        aoaDeg: flight.aoaDeg,
        throttle: flight.throttle,
      },
      seeker: W.state.seeker ? {
        centerX: W.state.seeker.centerX,
        centerY: W.state.seeker.centerY,
        gradientX: W.state.seeker.gradientX,
        gradientY: W.state.seeker.gradientY,
        objective: W.state.seeker.objective,
      } : null,
    };
    W.state.history.push(entry);
    if (W.state.history.length > W.state.follower.maxHistorySamples) W.state.history.shift();
  }

  W.stop = function () {
    clearTimers();
    if (W.state.channel) {
      W.state.channel.close();
      W.state.channel = null;
    }
    if (W.state.weatherHookInstalled && W.state.originalWeatherUpdate && window.weather) {
      window.weather.update = W.state.originalWeatherUpdate;
    }
    if (window.weather && W.state.originalWind) window.weather.currentWindVector = W.state.originalWind.slice();
    W.state.role = 'idle';
    W.state.leader = null;
    W.state.lastWake = null;
    W.state.lastRelative = null;
    W.state.lastControl = null;
    W.state.seeker = null;
    W.state.weatherHookInstalled = false;
    W.state.originalWeatherUpdate = null;
    W.state.originalWind = null;
    return W.status();
  };

  W.startLeader = async function (options = {}) {
    W.stop();
    await W.waitForGeoFS();
    W.state.role = 'leader';
    W.state.startedAtMs = performance.now();
    openChannel(options.session || 'b777-wake');
    await W.commandTrim(options);
    publishLeader();
    addTimer(publishLeader, Number.isFinite(options.publishPeriodMs) ? options.publishPeriodMs : 100);
    console.log('[geofsWake] leader running', W.status());
    return W.status();
  };

  W.startFollower = async function (options = {}) {
    W.stop();
    await W.waitForGeoFS();
    W.state.role = 'follower';
    W.state.startedAtMs = performance.now();
    openChannel(options.session || 'b777-wake');
    const leader = await waitForFreshLeader(Number.isFinite(options.leaderTimeoutMs) ? options.leaderTimeoutMs : 10000);

    const targetDownstreamM = Number.isFinite(options.targetDownstreamM) ? options.targetDownstreamM : 300;
    const initialCrossM = Number.isFinite(options.initialCrossM) ? options.initialCrossM : 0;
    const initialVerticalM = Number.isFinite(options.initialVerticalM) ? options.initialVerticalM : 0;
    W.state.follower = {
      targetDownstreamM,
      holdCrossM: Number.isFinite(options.holdCrossM) ? options.holdCrossM : initialCrossM,
      holdVerticalM: Number.isFinite(options.holdVerticalM) ? options.holdVerticalM : initialVerticalM,
      zeroAmbientWind: options.zeroAmbientWind !== false,
      downstreamSpeedGainKtPerM: Number.isFinite(options.downstreamSpeedGainKtPerM) ? options.downstreamSpeedGainKtPerM : 0.08,
      crossHeadingGainDegPerM: Number.isFinite(options.crossHeadingGainDegPerM) ? options.crossHeadingGainDegPerM : 0.08,
      maxSpeedCorrectionKt: Number.isFinite(options.maxSpeedCorrectionKt) ? options.maxSpeedCorrectionKt : 25,
      maxHeadingCorrectionDeg: Number.isFinite(options.maxHeadingCorrectionDeg) ? options.maxHeadingCorrectionDeg : 12,
      maxHistorySamples: Number.isFinite(options.maxHistorySamples) ? options.maxHistorySamples : 3600,
    };

    const mode = options.mode || (options.seek === false ? 'hold' : 'seek');
    if (!['hold', 'truth', 'seek'].includes(mode)) throw new Error('mode must be hold, truth, or seek.');
    W.state.guidanceMode = mode;
    W.state.seeker = W.newSeeker({ ...options.seeker, initialCrossM, initialVerticalM });

    const followerStart = W.positionBehindLeader(leader, targetDownstreamM, initialCrossM, initialVerticalM);
    const cl = W.finite(options.cl) ?? 0.5;
    const massKg = W.aircraftMassKg(options.massKg);
    const tasMps = W.trimTasMps(massKg, followerStart.altitudeM, cl);
    if (options.reposition !== false) {
      const placed = W.placeAircraft(followerStart, tasMps);
      if (!placed) console.warn('[geofsWake] Could not place follower behind leader. Continue from the current position.');
      await new Promise((r) => window.setTimeout(r, 500));
    }

    await W.commandTrim({
      ...options,
      cl,
      massKg,
      altitudeFt: followerStart.altitudeM / W.constants.FT_TO_M,
      headingDeg: leader.headingDeg,
      reposition: false,
    });

    W.installWeatherHook();
    wakePhysicsStep();
    controlStep();
    addTimer(wakePhysicsStep, Number.isFinite(options.wakePeriodMs) ? options.wakePeriodMs : 100);
    addTimer(controlStep, Number.isFinite(options.controlPeriodMs) ? options.controlPeriodMs : 1000);
    console.log('[geofsWake] follower running', W.status());
    return W.status();
  };

  W.status = function () {
    const flight = window.geofs?.aircraft?.instance ? W.flightState() : null;
    return {
      role: W.state.role,
      session: W.state.session,
      aircraft: window.geofs?.aircraft?.instance ? W.aircraftName() : null,
      trim: W.state.trim,
      guidanceMode: W.state.guidanceMode,
      leaderAgeMs: W.state.leader ? Date.now() - W.state.leader.timeMs : null,
      relative: W.state.lastRelative,
      wake: W.state.lastWake,
      injectedWindENU: W.state.injectedWindENU,
      control: W.state.lastControl,
      seeker: W.state.seeker,
      grid: W.state.gridMeta,
      flight,
      historySamples: W.state.history.length,
    };
  };

  W.guidance = W.guidance || {};
  W.guidance.setMode = function (mode) {
    if (!['hold', 'truth', 'seek'].includes(mode)) throw new Error('mode must be hold, truth, or seek.');
    W.state.guidanceMode = mode;
    return mode;
  };
  W.guidance.hold = function (crossM, verticalM) {
    if (!W.state.follower) throw new Error('Follower is not running.');
    W.state.follower.holdCrossM = Number(crossM);
    W.state.follower.holdVerticalM = Number(verticalM);
    W.state.guidanceMode = 'hold';
  };

  W.data = W.data || {};
  W.data.history = () => W.state.history.slice();
  W.data.clear = () => { W.state.history.length = 0; };
  W.data.csv = function () {
    const rows = ['timeSec,mode,downstreamM,crossM,verticalM,targetX,targetY,idealX,idealY,uMps,vMps,wMps,throttle,kias,altitudeFt,objective'];
    for (const h of W.state.history) {
      rows.push([
        h.timeSec, h.mode, h.relative.downstreamM, h.relative.crossM, h.relative.verticalM,
        h.target.xM, h.target.yM, h.ideal?.xM ?? '', h.ideal?.yM ?? '',
        h.wake.uMps, h.wake.vMps, h.wake.wMps, h.flight.throttle, h.flight.kias,
        h.flight.altitudeFt, h.seeker?.objective ?? '',
      ].join(','));
    }
    return rows.join('\n');
  };

  window.geofsWake = W;
  console.log('[geofsWake] runtime ready. Use geofsWake.startLeader() or geofsWake.startFollower().');
})();