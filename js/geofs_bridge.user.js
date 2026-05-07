// ==UserScript==
// @name         GeoFS Bridge
// @namespace    geofs_pilot
// @version      1.2.0
// @description  Connects GeoFS to a local autopilot control app.
// @match        *://www.geo-fs.com/*
// @match        *://geo-fs.com/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  // ===========================================================================
  // Config
  // ===========================================================================

  const CONFIG = {
    wsUrl: 'ws://127.0.0.1:52137',
    reconnectMs: 3000,
    telemetryHz: 30,
    tag: '[GeoFS Bridge]',
    version: '1.2.0',
  };

  // ===========================================================================
  // State
  // ===========================================================================

  const state = {
    ws: null,
    connected: false,
    bridgeId: null,
    label: '',
    seq: 0,
    lastTelemetrySendMs: 0,
    frameCallbackInstalled: false,
  };

  // ===========================================================================
  // Utilities
  // ===========================================================================

  function log(...args) {
    console.log(CONFIG.tag, ...args);
  }

  function warn(...args) {
    console.warn(CONFIG.tag, ...args);
  }

  function safeRead(fn, fallback = undefined) {
    try {
      const value = fn();
      return value === undefined || value === null ? fallback : value;
    } catch (_) {
      return fallback;
    }
  }

  function nowMs() {
    return performance.now();
  }

  function getBridgeId() {
    const key = 'geofs_bridge_id';
    let value = safeRead(() => window.sessionStorage.getItem(key), '');

    if (!value) {
      value = `tab_${Math.random().toString(36).slice(2, 10)}`;
      safeRead(() => window.sessionStorage.setItem(key, value));
    }

    return value;
  }

  function getAircraftName() {
    return safeRead(
      () => window.geofs.aircraft.instance.aircraftRecord.name,
      ''
    );
  }

  function getBridgeLabel() {
    const aircraft = getAircraftName() || 'GeoFS';
    const suffix = state.bridgeId ? state.bridgeId.slice(-4) : 'tab';
    return `${aircraft} ${suffix}`;
  }

  function numberOrNull(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function feetToMeters(feet) {
    return Number(feet) * 0.3048;
  }

  function metersToFeet(meters) {
    return Number(meters) / 0.3048;
  }

  function normalizeHeading(degrees) {
    return ((Number(degrees) % 360) + 360) % 360;
  }

  // ===========================================================================
  // GeoFS readiness
  // ===========================================================================

  function waitForGeoFS(callback) {
    const check = () => {
      const ready =
        window.geofs &&
        window.geofs.aircraft &&
        window.geofs.aircraft.instance &&
        window.geofs.api &&
        typeof window.geofs.api.addFrameCallback === 'function' &&
        window.controls &&
        typeof window.controls.update === 'function';

      if (ready) {
        log('GeoFS ready');
        callback();
      } else {
        setTimeout(check, 500);
      }
    };

    check();
  }

  // ===========================================================================
  // Telemetry
  // ===========================================================================

  function readTelemetry() {
    const g = window.geofs;
    const aircraft = safeRead(() => g.aircraft.instance, {});
    const anim = safeRead(() => g.animation.values, {});
    const autopilot = safeRead(() => g.autopilot, {});
    const lla = safeRead(() => aircraft.llaLocation, []);
    const altitudeFt = anim.altitude || metersToFeet(lla[2] || 0) || 0;

    return {
      type: 'telemetry',
      bridge_id: state.bridgeId,
      label: getBridgeLabel(),
      seq: state.seq++,
      ts_ms: nowMs(),
      aircraft: safeRead(() => aircraft.aircraftRecord.name, ''),
      lat_deg: numberOrNull(lla[0]),
      lon_deg: numberOrNull(lla[1]),
      altitude_ft: altitudeFt,
      heading_deg: anim.heading360 || safeRead(() => aircraft.htr[0], 0) || 0,
      speed_kts: anim.kias || anim.ktas || 0,
      vertical_speed_fpm: anim.verticalSpeed || 0,
      autopilot: {
        on: !!autopilot.on,
        mode: safeRead(() => autopilot.mode, ''),
        speed_mode: safeRead(() => autopilot.speedMode, ''),
        values: safeRead(
          () => JSON.parse(JSON.stringify(autopilot.values || {})),
          {}
        ),
      },
    };
  }

  function installTelemetryFrameCallback() {
    if (state.frameCallbackInstalled) return;

    const periodMs = 1000.0 / CONFIG.telemetryHz;

    window.geofs.api.addFrameCallback(function geofsBridgeTelemetryFrame() {
      if (!state.connected) return;

      const t = nowMs();
      if (t - state.lastTelemetrySendMs < periodMs) return;
      state.lastTelemetrySendMs = t;

      send(readTelemetry());
    });

    state.frameCallbackInstalled = true;
    log('Telemetry callback installed');
  }

  // ===========================================================================
  // WebSocket transport
  // ===========================================================================

  function connectWebSocket() {
    log(`Connecting to ${CONFIG.wsUrl}`);

    try {
      state.ws = new WebSocket(CONFIG.wsUrl);
    } catch (e) {
      warn('WebSocket constructor failed:', e);
      scheduleReconnect();
      return;
    }

    state.ws.onopen = () => {
      state.connected = true;
      state.label = getBridgeLabel();
      log('Connected');

      send({
        type: 'hello',
        bridge_id: state.bridgeId,
        version: CONFIG.version,
        label: state.label,
        page_title: safeRead(() => window.document.title, ''),
        mode: 'formation_telemetry_plus_autopilot_commands',
        aircraft: getAircraftName(),
      });
    };

    state.ws.onmessage = (event) => {
      handleServerMessage(event.data);
    };

    state.ws.onclose = () => {
      state.connected = false;
      log('Disconnected');
      scheduleReconnect();
    };

    state.ws.onerror = (e) => {
      warn('WebSocket error:', e);
    };
  }

  function scheduleReconnect() {
    setTimeout(connectWebSocket, CONFIG.reconnectMs);
  }

  function send(obj) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
      try {
        state.ws.send(JSON.stringify(obj));
      } catch (e) {
        warn('send failed:', e);
      }
    }
  }

  function handleServerMessage(raw) {
    let msg;
    try {
      msg = JSON.parse(raw);
    } catch (_) {
      return;
    }

    switch (msg.type) {
      case 'ack':
        log('Server ack:', msg);
        break;

      case 'ping':
        send({ type: 'pong', ts_ms: nowMs() });
        break;

      case 'autopilot_command':
        if (msg.bridge_id === state.bridgeId) {
          handleAutopilotCommand(msg);
        }
        break;

      default:
        // Unknown messages are ignored intentionally.
        break;
    }
  }

  // ===========================================================================
  // Pose reset
  // ===========================================================================

  function setAircraftPose(pose) {
    const aircraft = safeRead(() => window.geofs.aircraft.instance, null);
    if (!aircraft || !pose) return;

    const lat = numberOrNull(pose.lat_deg);
    const lon = numberOrNull(pose.lon_deg);
    const altitudeFt = numberOrNull(pose.altitude_ft);
    const heading = normalizeHeading(pose.heading_deg || 0);

    if (lat == null || lon == null || altitudeFt == null) return;

    const lla = [lat, lon, feetToMeters(altitudeFt)];

    if (typeof window.geofs?.api?.setAircraftPosition === 'function') {
      window.geofs.api.setAircraftPosition(lla, heading);
    } else {
      aircraft.llaLocation = lla;
      if (Array.isArray(aircraft.htr)) {
        aircraft.htr[0] = heading;
        aircraft.htr[1] = 0;
        aircraft.htr[2] = 0;
      } else {
        aircraft.htr = [heading, 0, 0];
      }
    }

    if (Array.isArray(aircraft.rigidBody?.velocity)) {
      aircraft.rigidBody.velocity = [0, 0, 0];
    }
    if (typeof aircraft.rigidBody?.setVelocity === 'function') {
      aircraft.rigidBody.setVelocity([0, 0, 0]);
    }

    safeRead(() => window.geofs.camera?.update?.(0));
  }

  function resetToPose(pose) {
    setAircraftPose(pose);
    const autopilot = getAutopilot();
    const altitude = numberOrNull(pose?.altitude_ft);
    const speed = numberOrNull(pose?.speed_kts);
    const heading = numberOrNull(pose?.heading_deg);

    if (!autopilot) return;
    ensureAutopilotOn(autopilot);
    if (heading != null && typeof autopilot.setCourse === 'function') {
      setAutopilotMode(autopilot, 'HDG');
      autopilot.setCourse(heading);
    }
    if (altitude != null && typeof autopilot.setAltitude === 'function') {
      autopilot.setAltitude(altitude);
    }
    if (speed != null && typeof autopilot.setSpeed === 'function') {
      autopilot.setSpeed(speed);
    }
  }

  // ===========================================================================
  // Autopilot commands
  // ===========================================================================

  function getAutopilot() {
    return window.geofs?.autopilot || null;
  }

  function ensureAutopilotOn(autopilot) {
    if (!autopilot || autopilot.on) return;
    if (typeof autopilot.turnOn === 'function') {
      autopilot.turnOn();
    }
  }

  function setAutopilotMode(autopilot, mode) {
    if (!autopilot || !mode) return;
    if (typeof autopilot.setMode === 'function') {
      autopilot.setMode(mode);
    }
  }

  function handleAutopilotCommand(msg) {
    const autopilot = getAutopilot();

    if (!autopilot && msg.command !== 'reset_pose') {
      warn('GeoFS autopilot unavailable');
      return;
    }

    const value = numberOrNull(msg.value);

    try {
      switch (msg.command) {
        case 'reset_pose':
          resetToPose(msg.pose);
          log('Aircraft reset to formation pose:', msg.pose);
          break;

        case 'turn_on':
          ensureAutopilotOn(autopilot);
          log('Autopilot turned on');
          break;

        case 'turn_off':
          if (typeof autopilot.turnOff === 'function') {
            autopilot.turnOff();
          }
          log('Autopilot turned off');
          break;

        case 'set_mode':
          setAutopilotMode(autopilot, msg.mode);
          log('Autopilot mode set:', msg.mode);
          break;

        case 'set_heading':
          if (value == null || typeof autopilot.setCourse !== 'function') return;
          ensureAutopilotOn(autopilot);
          setAutopilotMode(autopilot, 'HDG');
          autopilot.setCourse(value);
          log('Autopilot heading set:', value);
          break;

        case 'set_altitude':
          if (value == null || typeof autopilot.setAltitude !== 'function') return;
          ensureAutopilotOn(autopilot);
          autopilot.setAltitude(value);
          log('Autopilot altitude set:', value);
          break;

        case 'set_speed':
          if (value == null || typeof autopilot.setSpeed !== 'function') return;
          ensureAutopilotOn(autopilot);
          autopilot.setSpeed(value);
          log('Autopilot speed set:', value);
          break;

        case 'set_vertical_speed':
          if (
            value == null ||
            typeof autopilot.setVerticalSpeed !== 'function'
          ) {
            return;
          }
          ensureAutopilotOn(autopilot);
          autopilot.setVerticalSpeed(value);
          log('Autopilot vertical speed set:', value);
          break;

        default:
          warn('Unknown autopilot command:', msg.command);
          break;
      }
    } catch (e) {
      warn('Autopilot command failed:', msg, e);
    }
  }

  // ===========================================================================
  // Entry point
  // ===========================================================================

  waitForGeoFS(() => {
    state.bridgeId = getBridgeId();
    state.label = getBridgeLabel();
    installTelemetryFrameCallback();
    connectWebSocket();

    window.__geofsBridge = {
      reconnect: () => {
        if (state.ws) state.ws.close();
      },
      status: () => ({
        connected: state.connected,
        ws_ready_state: state.ws ? state.ws.readyState : null,
        seq: state.seq,
      }),
    };

    log('Debug API installed: window.__geofsBridge');
  });

})();
