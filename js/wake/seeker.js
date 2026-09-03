(function () {
  'use strict';

  const W = window.GeoFSWake;
  if (!W) throw new Error('GeoFSWake core must load before seeker.js');

  W.newSeeker = function (options = {}) {
    const now = performance.now() / 1000;
    return {
      startedSec: now,
      lastSec: now,
      centerX: Number.isFinite(options.initialCrossM) ? options.initialCrossM : 0,
      centerY: Number.isFinite(options.initialVerticalM) ? options.initialVerticalM : 0,
      commandX: 0,
      commandY: 0,
      amplitudeX: Number.isFinite(options.amplitudeCrossM) ? options.amplitudeCrossM : 7,
      amplitudeY: Number.isFinite(options.amplitudeVerticalM) ? options.amplitudeVerticalM : 4,
      omegaX: 2 * Math.PI / (Number.isFinite(options.periodCrossSec) ? options.periodCrossSec : 44),
      omegaY: 2 * Math.PI / (Number.isFinite(options.periodVerticalSec) ? options.periodVerticalSec : 61),
      phaseY: Math.PI / 2,
      gainX: Number.isFinite(options.gainCross) ? options.gainCross : 2.0,
      gainY: Number.isFinite(options.gainVertical) ? options.gainVertical : 1.5,
      warmupSec: Number.isFinite(options.warmupSec) ? options.warmupSec : 20,
      objectiveMean: null,
      gradientX: 0,
      gradientY: 0,
      objective: null,
      highPass: 0,
      minX: Number.isFinite(options.minCrossM) ? options.minCrossM : -70,
      maxX: Number.isFinite(options.maxCrossM) ? options.maxCrossM : 70,
      minY: Number.isFinite(options.minVerticalM) ? options.minVerticalM : -40,
      maxY: Number.isFinite(options.maxVerticalM) ? options.maxVerticalM : 40,
    };
  };

  W.measuredObjective = function (flight, altitudeTargetFt) {
    const throttle = Number.isFinite(flight.throttle) ? flight.throttle : 1;
    const altitudeError = Number.isFinite(altitudeTargetFt) ? flight.altitudeFt - altitudeTargetFt : 0;
    const vs = Number.isFinite(flight.verticalSpeedFpm) ? flight.verticalSpeedFpm : 0;
    const roll = Number.isFinite(flight.rollDeg) ? flight.rollDeg : 0;
    return (1 - throttle)
      - 0.000002 * altitudeError * altitudeError
      - 0.00000015 * vs * vs
      - 0.00008 * roll * roll;
  };

  W.updateSeeker = function (s, timeSec, objective) {
    if (!Number.isFinite(objective)) return { xM: s.commandX, yM: s.commandY };
    const dt = W.clamp(timeSec - s.lastSec, 0.02, 1.0);
    s.lastSec = timeSec;
    const elapsed = timeSec - s.startedSec;
    const sx = Math.sin(s.omegaX * elapsed);
    const sy = Math.sin(s.omegaY * elapsed + s.phaseY);

    if (s.objectiveMean === null) s.objectiveMean = objective;
    const meanAlpha = 1 - Math.exp(-dt / 20);
    s.objectiveMean += meanAlpha * (objective - s.objectiveMean);
    const hp = objective - s.objectiveMean;
    const gradAlpha = 1 - Math.exp(-dt / 8);
    s.gradientX += gradAlpha * ((hp * sx) - s.gradientX);
    s.gradientY += gradAlpha * ((hp * sy) - s.gradientY);

    if (elapsed >= s.warmupSec) {
      s.centerX = W.clamp(s.centerX + s.gainX * s.gradientX * dt, s.minX, s.maxX);
      s.centerY = W.clamp(s.centerY + s.gainY * s.gradientY * dt, s.minY, s.maxY);
    }

    s.commandX = W.clamp(s.centerX + s.amplitudeX * sx, s.minX, s.maxX);
    s.commandY = W.clamp(s.centerY + s.amplitudeY * sy, s.minY, s.maxY);
    s.objective = objective;
    s.highPass = hp;
    return { xM: s.commandX, yM: s.commandY };
  };
})();