(function () {
  'use strict';

  const W = window.GeoFSWake = window.GeoFSWake || {};
  const C = W.constants = Object.freeze({
    G: 9.80665,
    FT_TO_M: 0.3048,
    KNOT_TO_MPS: 0.514444,
    RHO0: 1.225,
    EARTH_RADIUS_M: 6371000,
    DEG_TO_RAD: Math.PI / 180,
    RAD_TO_DEG: 180 / Math.PI,
    aircraft: Object.freeze({
      name: 'Boeing 777-200',
      wingAreaM2: 427.8,
      spanM: 60.93,
      fallbackMassKg: 200000,
    }),
  });

  W.state = W.state || {
    role: 'idle',
    session: 'b777-wake',
    channel: null,
    timers: [],
    leader: null,
    trim: null,
    grid: null,
    gridMeta: null,
    follower: null,
    seeker: null,
    guidanceMode: 'seek',
    lastWake: null,
    lastRelative: null,
    lastControl: null,
    originalWind: null,
    originalWeatherUpdate: null,
    weatherHookInstalled: false,
    injectedWindENU: [0, 0, 0],
    history: [],
    startedAtMs: 0,
  };

  const finite = W.finite = (v) => {
    if (v === null || v === undefined || v === '') return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };
  W.clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  W.wrap360 = (d) => ((d % 360) + 360) % 360;

  W.waitForGeoFS = function () {
    return new Promise((resolve) => {
      const poll = () => {
        if (window.geofs?.aircraft?.instance && window.geofs?.animation?.values && window.controls) {
          resolve();
          return;
        }
        window.setTimeout(poll, 250);
      };
      poll();
    });
  };

  W.isaDensity = function (altitudeM) {
    const h = Math.max(0, Number(altitudeM));
    const R = 287.05287;
    if (h <= 11000) {
      const T0 = 288.15;
      const P0 = 101325;
      const L = -0.0065;
      const T = T0 + L * h;
      const P = P0 * Math.pow(T / T0, -C.G / (L * R));
      return P / (R * T);
    }
    const T11 = 216.65;
    const P11 = 22632.06;
    return P11 * Math.exp((-C.G * (h - 11000)) / (R * T11)) / (R * T11);
  };

  W.trimTasMps = function (massKg, altitudeM, cl) {
    return Math.sqrt((2 * massKg * C.G) / (W.isaDensity(altitudeM) * C.aircraft.wingAreaM2 * cl));
  };

  W.trimKias = function (massKg, cl) {
    return Math.sqrt((2 * massKg * C.G) / (C.RHO0 * C.aircraft.wingAreaM2 * cl)) / C.KNOT_TO_MPS;
  };

  W.aircraftName = function () {
    const a = window.geofs?.aircraft?.instance;
    return String(a?.definition?.name || a?.aircraftRecord?.name || a?.name || a?.id || 'unknown aircraft');
  };

  W.aircraftMassKg = function (override) {
    const specified = finite(override);
    if (specified && specified > 1000) return specified;
    const a = window.geofs?.aircraft?.instance;
    for (const v of [a?.rigidBody?.mass, a?.mass, a?.definition?.mass, a?.aircraftRecord?.mass]) {
      const m = finite(v);
      if (m && m > 1000) return m;
    }
    console.warn(`[geofsWake] Using fallback mass ${C.aircraft.fallbackMassKg} kg.`);
    return C.aircraft.fallbackMassKg;
  };

  W.flightState = function () {
    const a = window.geofs?.aircraft?.instance;
    const av = window.geofs?.animation?.values || {};
    const lla = a?.llaLocation || a?.lla || [];
    return {
      timeMs: Date.now(),
      latDeg: finite(lla[0]),
      lonDeg: finite(lla[1]),
      altitudeM: finite(lla[2]) ?? (finite(av.altitude) ?? 0) * C.FT_TO_M,
      altitudeFt: finite(av.altitude) ?? (finite(lla[2]) ?? 0) / C.FT_TO_M,
      headingDeg: finite(av.heading360) ?? finite(a?.htr?.[0]) ?? 0,
      pitchDeg: finite(av.atilt) ?? finite(a?.htr?.[1]),
      rollDeg: finite(av.aroll) ?? finite(a?.htr?.[2]),
      kias: finite(av.kias),
      tasKt: finite(av.ktas) ?? ((finite(a?.trueAirSpeed) ?? 0) / C.KNOT_TO_MPS),
      verticalSpeedFpm: finite(av.verticalSpeed) ?? 0,
      aoaDeg: finite(av.aoa),
      loadFactor: finite(av.loadFactor),
      throttle: finite(window.controls?.throttle),
    };
  };

  function invokeFirst(candidates) {
    for (const c of candidates) {
      if (!c.target || typeof c.target[c.name] !== 'function') continue;
      c.target[c.name](...(c.args || []));
      return true;
    }
    return false;
  }

  function setFirstProperty(target, names, value) {
    for (const name of names) {
      if (target && name in target) {
        target[name] = value;
        return true;
      }
    }
    return false;
  }

  W.setAutopilotTargets = function ({ headingDeg, altitudeFt, speedKias }) {
    const ap = window.geofs?.autopilot;
    if (!ap) throw new Error('GeoFS autopilot is not available.');
    const heading = W.wrap360(headingDeg);
    const h = invokeFirst([
      { target: ap, name: 'setCourse', args: [heading] },
      { target: ap, name: 'setHeading', args: [heading] },
    ]) || setFirstProperty(ap, ['heading', 'headingBug', 'course'], heading);
    const a = invokeFirst([
      { target: ap, name: 'setAltitude', args: [altitudeFt] },
      { target: ap, name: 'setAltitudeHold', args: [altitudeFt] },
    ]) || setFirstProperty(ap, ['altitude', 'altitudeHold', 'targetAltitude'], altitudeFt);
    if (typeof ap.setSpeedMode === 'function') ap.setSpeedMode('knots');
    const s = invokeFirst([
      { target: ap, name: 'setSpeed', args: [speedKias] },
      { target: ap, name: 'setAirSpeed', args: [speedKias] },
    ]) || setFirstProperty(ap, ['speed', 'airspeed', 'targetSpeed'], speedKias);
    if (!h || !a || !s) throw new Error('GeoFS autopilot target API is incomplete.');
  };

  W.enableAutopilot = function () {
    const ap = window.geofs?.autopilot;
    if (!ap) throw new Error('GeoFS autopilot is not available.');
    if (invokeFirst([
      { target: ap, name: 'turnOn' },
      { target: ap, name: 'setEnabled', args: [true] },
      { target: ap, name: 'set', args: [true] },
    ])) return;
    const enabled = [ap.on, ap.enabled, ap.isOn, ap.active].find((v) => typeof v === 'boolean');
    const toggle = window.controls?.setters?.toggleAutoPilot;
    if (typeof toggle === 'function' && enabled !== undefined) {
      if (!enabled) toggle();
      return;
    }
    throw new Error('GeoFS autopilot enable API is not available.');
  };

  W.placeAircraft = function (p, speedMps) {
    const a = window.geofs?.aircraft?.instance;
    if (!a) return false;
    if (invokeFirst([
      { target: window.geofs?.api, name: 'setAircraftPosition', args: [p.latDeg, p.lonDeg, p.altitudeM, p.headingDeg, speedMps] },
      { target: a, name: 'setPosition', args: [p.latDeg, p.lonDeg, p.altitudeM, p.headingDeg, speedMps] },
    ])) return true;
    if (typeof a.place === 'function') {
      a.place([p.latDeg, p.lonDeg, p.altitudeM], [p.headingDeg, 0, 0]);
      return true;
    }
    return false;
  };

  W.commandTrim = async function (options = {}) {
    await W.waitForGeoFS();
    const selected = W.aircraftName();
    if (!/777/.test(selected) || !/200/.test(selected)) console.warn(`[geofsWake] Select the ${C.aircraft.name}. Current: ${selected}`);
    const cl = finite(options.cl) ?? 0.5;
    const massKg = W.aircraftMassKg(options.massKg);
    const f = W.flightState();
    const altitudeFt = finite(options.altitudeFt) ?? (f.altitudeFt > 2000 ? f.altitudeFt : 10000);
    const headingDeg = finite(options.headingDeg) ?? f.headingDeg;
    const altitudeM = altitudeFt * C.FT_TO_M;
    const tasMps = W.trimTasMps(massKg, altitudeM, cl);
    const speedKias = W.trimKias(massKg, cl);
    if (f.altitudeFt < 2000 && options.reposition !== false && f.latDeg != null && f.lonDeg != null) {
      W.placeAircraft({ latDeg: f.latDeg, lonDeg: f.lonDeg, altitudeM, headingDeg }, tasMps);
      await new Promise((r) => window.setTimeout(r, 400));
    }
    W.setAutopilotTargets({ headingDeg, altitudeFt, speedKias });
    W.enableAutopilot();
    W.state.trim = { cl, massKg, altitudeFt, headingDeg, speedKias, targetTasKt: tasMps / C.KNOT_TO_MPS };
    return W.state.trim;
  };

  W.relativeToLeader = function (leader, follower) {
    const lat = leader.latDeg * C.DEG_TO_RAD;
    const east = (follower.lonDeg - leader.lonDeg) * C.DEG_TO_RAD * Math.cos(lat) * C.EARTH_RADIUS_M;
    const north = (follower.latDeg - leader.latDeg) * C.DEG_TO_RAD * C.EARTH_RADIUS_M;
    const up = follower.altitudeM - leader.altitudeM;
    const h = leader.headingDeg * C.DEG_TO_RAD;
    const forward = east * Math.sin(h) + north * Math.cos(h);
    return {
      downstreamM: -forward,
      crossM: east * Math.cos(h) - north * Math.sin(h),
      verticalM: up,
      eastM: east,
      northM: north,
      upM: up,
    };
  };

  W.positionBehindLeader = function (leader, downstreamM, crossM, verticalM) {
    const h = leader.headingDeg * C.DEG_TO_RAD;
    const east = -downstreamM * Math.sin(h) + crossM * Math.cos(h);
    const north = -downstreamM * Math.cos(h) - crossM * Math.sin(h);
    const lat = leader.latDeg * C.DEG_TO_RAD;
    return {
      latDeg: leader.latDeg + (north / C.EARTH_RADIUS_M) * C.RAD_TO_DEG,
      lonDeg: leader.lonDeg + (east / (C.EARTH_RADIUS_M * Math.max(0.05, Math.cos(lat)))) * C.RAD_TO_DEG,
      altitudeM: leader.altitudeM + verticalM,
      headingDeg: leader.headingDeg,
    };
  };

  W.injectWakeWind = function (sample, leaderHeadingDeg, zeroAmbientWind = true) {
    const weather = window.weather;
    if (!weather) throw new Error('GeoFS weather object is not available.');
    const h = leaderHeadingDeg * C.DEG_TO_RAD;
    const eastAirMass = sample.uMps * Math.sin(h) + sample.vMps * Math.cos(h);
    const northAirMass = sample.uMps * Math.cos(h) - sample.vMps * Math.sin(h);
    const base = zeroAmbientWind ? [0, 0, 0] : (W.state.originalWind || [0, 0, 0]);
    const vec = [base[0] - eastAirMass, base[1] - northAirMass, base[2] - sample.wMps];
    weather.currentWindVector = vec;
    const speed = Math.hypot(...vec);
    weather.currentWindSpeedMs = speed;
    weather.currentWindSpeed = speed / C.KNOT_TO_MPS;
    weather.currentWindDirection = Math.hypot(vec[0], vec[1]) > 1e-6 ? W.wrap360(Math.atan2(vec[0], vec[1]) * C.RAD_TO_DEG) : 0;
    weather.windActive = speed > 1e-6;
    W.state.injectedWindENU = vec.slice();
  };

  W.installWeatherHook = function () {
    if (W.state.weatherHookInstalled || !window.weather) return;
    W.state.originalWind = Array.isArray(window.weather.currentWindVector) ? window.weather.currentWindVector.slice(0, 3) : [0, 0, 0];
    if (typeof window.weather.update === 'function') {
      W.state.originalWeatherUpdate = window.weather.update;
      window.weather.update = function (...args) {
        const out = W.state.originalWeatherUpdate.apply(this, args);
        if (W.state.role === 'follower' && W.state.lastWake && W.state.leader) {
          W.injectWakeWind(W.state.lastWake, W.state.leader.headingDeg, W.state.follower?.zeroAmbientWind !== false);
        }
        return out;
      };
    }
    W.state.weatherHookInstalled = true;
  };
})();