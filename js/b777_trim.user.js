// ==UserScript==
// @name         GeoFS Boeing 777-200 CL Trim
// @namespace    geofs_trim
// @version      1.0.0
// @description  Fly the GeoFS Boeing 777-200 at a level trim condition for a target lift coefficient.
// @match        https://www.geo-fs.com/geofs.php*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  const G = 9.80665;
  const FT_TO_M = 0.3048;
  const KNOT_TO_MPS = 0.514444;

  const AIRCRAFT = Object.freeze({
    name: 'Boeing 777-200',
    wingAreaM2: 427.8,
    fallbackMassKg: 200000,
  });

  const DEFAULTS = Object.freeze({
    cl: 0.5,
    altitudeFt: 10000,
    settleSeconds: 5,
    speedToleranceKt: 2,
    altitudeToleranceFt: 60,
    verticalSpeedToleranceFpm: 120,
  });

  const state = {
    active: false,
    monitorTimer: null,
    command: null,
    stableSamples: 0,
  };

  const finite = (value) => {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  };

  function waitForGeoFS() {
    return new Promise((resolve) => {
      const poll = () => {
        if (window.geofs?.aircraft?.instance && window.geofs?.animation?.values) {
          resolve();
          return;
        }
        window.setTimeout(poll, 250);
      };
      poll();
    });
  }

  function isaDensity(altitudeM) {
    const h = Math.max(0, Number(altitudeM));
    const r = 287.05287;
    const g0 = 9.80665;

    if (h <= 11000) {
      const t0 = 288.15;
      const p0 = 101325;
      const lapse = -0.0065;
      const t = t0 + lapse * h;
      const p = p0 * Math.pow(t / t0, -g0 / (lapse * r));
      return p / (r * t);
    }

    const t11 = 216.65;
    const p11 = 22632.06;
    const p = p11 * Math.exp((-g0 * (h - 11000)) / (r * t11));
    return p / (r * t11);
  }

  function trimTasMps(massKg, altitudeM, cl) {
    const rho = isaDensity(altitudeM);
    return Math.sqrt((2 * massKg * G) / (rho * AIRCRAFT.wingAreaM2 * cl));
  }

  function aircraftName() {
    const a = window.geofs?.aircraft?.instance;
    return String(
      a?.definition?.name ||
      a?.aircraftRecord?.name ||
      a?.name ||
      a?.id ||
      'unknown aircraft'
    );
  }

  function aircraftMassKg(overrideMassKg) {
    const override = finite(overrideMassKg);
    if (override && override > 1000) return override;

    const a = window.geofs?.aircraft?.instance;
    const candidates = [
      a?.rigidBody?.mass,
      a?.mass,
      a?.definition?.mass,
      a?.aircraftRecord?.mass,
    ];

    for (const value of candidates) {
      const mass = finite(value);
      if (mass && mass > 1000) return mass;
    }

    console.warn(
      `[b777Trim] GeoFS mass was not available. Using ${AIRCRAFT.fallbackMassKg} kg. ` +
      'Pass { massKg: ... } to start() if you need another mass.'
    );
    return AIRCRAFT.fallbackMassKg;
  }

  function currentFlightState() {
    const a = window.geofs?.aircraft?.instance;
    const av = window.geofs?.animation?.values || {};
    const lla = a?.llaLocation || a?.lla || [];

    return {
      latDeg: finite(lla[0]),
      lonDeg: finite(lla[1]),
      altitudeM: finite(lla[2]) ?? (finite(av.altitude) ?? 0) * FT_TO_M,
      altitudeFt: finite(av.altitude) ?? (finite(lla[2]) ?? 0) / FT_TO_M,
      headingDeg: finite(av.heading360) ?? finite(a?.htr?.[0]) ?? 0,
      tasKt: finite(av.ktas) ?? ((finite(a?.trueAirSpeed) ?? 0) / KNOT_TO_MPS),
      verticalSpeedFpm: finite(av.verticalSpeed) ?? 0,
      aoaDeg: finite(av.aoa),
      pitchDeg: finite(av.atilt),
      throttle: finite(window.controls?.throttle),
    };
  }

  function invokeFirst(candidates) {
    for (const candidate of candidates) {
      const target = candidate.target;
      if (!target || typeof target[candidate.name] !== 'function') continue;
      target[candidate.name](...(candidate.args || []));
      return candidate.via || candidate.name;
    }
    return null;
  }

  function setExistingNumber(target, names, value) {
    for (const name of names) {
      if (target && name in target) {
        target[name] = value;
        return name;
      }
    }
    return null;
  }

  function setAutopilotTargets({ headingDeg, altitudeFt, speedKt }) {
    const ap = window.geofs?.autopilot;
    if (!ap) throw new Error('GeoFS autopilot is not available.');

    const headingVia =
      invokeFirst([
        { target: ap, name: 'setCourse', args: [headingDeg], via: 'autopilot.setCourse' },
        { target: ap, name: 'setHeading', args: [headingDeg], via: 'autopilot.setHeading' },
      ]) ||
      setExistingNumber(ap, ['heading', 'headingBug', 'course'], headingDeg);

    const altitudeVia =
      invokeFirst([
        { target: ap, name: 'setAltitude', args: [altitudeFt], via: 'autopilot.setAltitude' },
        { target: ap, name: 'setAltitudeHold', args: [altitudeFt], via: 'autopilot.setAltitudeHold' },
      ]) ||
      setExistingNumber(ap, ['altitude', 'altitudeHold', 'targetAltitude'], altitudeFt);

    const speedVia =
      invokeFirst([
        { target: ap, name: 'setSpeed', args: [speedKt], via: 'autopilot.setSpeed' },
        { target: ap, name: 'setAirSpeed', args: [speedKt], via: 'autopilot.setAirSpeed' },
      ]) ||
      setExistingNumber(ap, ['speed', 'airspeed', 'targetSpeed'], speedKt);

    if (!headingVia || !altitudeVia || !speedVia) {
      throw new Error(
        `GeoFS autopilot target API is incomplete: heading=${headingVia}, ` +
        `altitude=${altitudeVia}, speed=${speedVia}`
      );
    }
  }

  function enableAutopilot() {
    const ap = window.geofs?.autopilot;
    if (!ap) throw new Error('GeoFS autopilot is not available.');

    const direct = invokeFirst([
      { target: ap, name: 'turnOn', via: 'autopilot.turnOn' },
      { target: ap, name: 'setEnabled', args: [true], via: 'autopilot.setEnabled' },
      { target: ap, name: 'set', args: [true], via: 'autopilot.set' },
    ]);
    if (direct) return direct;

    const current = [ap.on, ap.enabled, ap.isOn, ap.active].find((v) => typeof v === 'boolean');
    const toggle = window.controls?.setters?.toggleAutoPilot;
    if (typeof toggle === 'function' && current !== undefined) {
      if (!current) toggle();
      return 'controls.setters.toggleAutoPilot';
    }

    throw new Error('GeoFS autopilot enable API is not available.');
  }

  function moveToAltitude(altitudeFt, speedMps, headingDeg) {
    const a = window.geofs?.aircraft?.instance;
    const flight = currentFlightState();
    if (!a || flight.latDeg == null || flight.lonDeg == null) return false;

    const altitudeM = altitudeFt * FT_TO_M;
    const via = invokeFirst([
      {
        target: window.geofs?.api,
        name: 'setAircraftPosition',
        args: [flight.latDeg, flight.lonDeg, altitudeM, headingDeg, speedMps],
        via: 'geofs.api.setAircraftPosition',
      },
      {
        target: a,
        name: 'setPosition',
        args: [flight.latDeg, flight.lonDeg, altitudeM, headingDeg, speedMps],
        via: 'aircraft.setPosition',
      },
      {
        target: a,
        name: 'setLocation',
        args: [flight.latDeg, flight.lonDeg, altitudeM, headingDeg, speedMps],
        via: 'aircraft.setLocation',
      },
    ]);

    if (via) return true;

    const lla = Array.isArray(a.llaLocation) ? a.llaLocation : Array.isArray(a.lla) ? a.lla : null;
    if (!lla) return false;
    lla[2] = altitudeM;
    if (Array.isArray(a.lastLlaLocation)) a.lastLlaLocation[2] = altitudeM;
    if ('trueAirSpeed' in a) a.trueAirSpeed = speedMps;
    return true;
  }

  function estimatedCl(massKg, altitudeM, tasKt) {
    const tasMps = tasKt * KNOT_TO_MPS;
    if (!(tasMps > 1)) return null;
    const q = 0.5 * isaDensity(altitudeM) * tasMps * tasMps;
    return (massKg * G) / (q * AIRCRAFT.wingAreaM2);
  }

  function status() {
    if (!state.command) return { active: false };

    const flight = currentFlightState();
    const cl = estimatedCl(state.command.massKg, flight.altitudeM, flight.tasKt);
    const speedErrorKt = flight.tasKt - state.command.speedKt;
    const altitudeErrorFt = flight.altitudeFt - state.command.altitudeFt;

    return {
      active: state.active,
      aircraft: aircraftName(),
      targetCl: state.command.cl,
      estimatedCl: cl,
      massKg: state.command.massKg,
      wingAreaM2: AIRCRAFT.wingAreaM2,
      densityKgM3: isaDensity(flight.altitudeM),
      targetSpeedKt: state.command.speedKt,
      tasKt: flight.tasKt,
      speedErrorKt,
      targetAltitudeFt: state.command.altitudeFt,
      altitudeFt: flight.altitudeFt,
      altitudeErrorFt,
      verticalSpeedFpm: flight.verticalSpeedFpm,
      aoaDeg: flight.aoaDeg,
      pitchDeg: flight.pitchDeg,
      throttle: flight.throttle,
    };
  }

  function stopMonitor() {
    if (state.monitorTimer) window.clearInterval(state.monitorTimer);
    state.monitorTimer = null;
    state.stableSamples = 0;
  }

  function startMonitor() {
    stopMonitor();
    state.monitorTimer = window.setInterval(() => {
      if (!state.active || !state.command) return;
      const s = status();
      const cfg = state.command;
      const stable =
        Math.abs(s.speedErrorKt) <= cfg.speedToleranceKt &&
        Math.abs(s.altitudeErrorFt) <= cfg.altitudeToleranceFt &&
        Math.abs(s.verticalSpeedFpm) <= cfg.verticalSpeedToleranceFpm;

      state.stableSamples = stable ? state.stableSamples + 1 : 0;
      if (state.stableSamples === cfg.settleSeconds) {
        console.log('[b777Trim] trim converged', s);
      }
    }, 1000);
  }

  async function start(options = {}) {
    await waitForGeoFS();

    const selected = aircraftName();
    if (!/777/.test(selected) || !/200/.test(selected)) {
      console.warn(
        `[b777Trim] Selected aircraft is "${selected}". ` +
        `Select the ${AIRCRAFT.name} in GeoFS for the intended model.`
      );
    }

    const cl = finite(options.cl) ?? DEFAULTS.cl;
    if (!(cl > 0)) throw new Error('cl must be greater than zero.');

    const massKg = aircraftMassKg(options.massKg);
    const initial = currentFlightState();
    const altitudeFt = finite(options.altitudeFt) ??
      (initial.altitudeFt > 2000 ? initial.altitudeFt : DEFAULTS.altitudeFt);
    const altitudeM = altitudeFt * FT_TO_M;
    const headingDeg = finite(options.headingDeg) ?? initial.headingDeg;
    const speedMps = trimTasMps(massKg, altitudeM, cl);
    const speedKt = speedMps / KNOT_TO_MPS;

    if (initial.altitudeFt < 2000 && options.reposition !== false) {
      const moved = moveToAltitude(altitudeFt, speedMps, headingDeg);
      if (!moved) {
        console.warn('[b777Trim] Could not reposition the aircraft. Start airborne or set reposition:false.');
      }
    }

    setAutopilotTargets({ headingDeg, altitudeFt, speedKt });
    enableAutopilot();

    state.command = {
      cl,
      massKg,
      altitudeFt,
      headingDeg,
      speedKt,
      settleSeconds: finite(options.settleSeconds) ?? DEFAULTS.settleSeconds,
      speedToleranceKt: finite(options.speedToleranceKt) ?? DEFAULTS.speedToleranceKt,
      altitudeToleranceFt: finite(options.altitudeToleranceFt) ?? DEFAULTS.altitudeToleranceFt,
      verticalSpeedToleranceFpm:
        finite(options.verticalSpeedToleranceFpm) ?? DEFAULTS.verticalSpeedToleranceFpm,
    };
    state.active = true;
    startMonitor();

    const result = status();
    console.log('[b777Trim] commanded CL trim', result);
    return result;
  }

  function stop() {
    state.active = false;
    stopMonitor();
    return status();
  }

  window.b777Trim = Object.freeze({
    aircraft: AIRCRAFT,
    start,
    stop,
    status,
    isaDensity,
    trimTasMps,
  });

  console.log('[b777Trim] ready. Run b777Trim.start()');
})();
