// ==UserScript==
// @name         GeoFS Bridge
// @namespace    geofs_pilot
// @version      1.1.0
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
    version: '1.1.0',
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
    const controls = window.controls || {};
    const autopilot = safeRead(() => g.autopilot, {});
    const altitudeFt = anim.altitude || 0;

    return {
      type: 'telemetry',
      bridge_id: state.bridgeId,
      label: getBridgeLabel(),
      seq: state.seq++,
      ts_ms: nowMs(),
      aircraft: safeRead(() => aircraft.aircraftRecord.name, ''),
      altitude_ft: altitudeFt,
      heading_deg: anim.heading360 || 0,
      speed_kts: anim.kias || 0,
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
        mode: 'telemetry_plus_autopilot_commands',
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

    if (!autopilot) {
      warn('GeoFS autopilot unavailable');
      return;
    }

    const value = numberOrNull(msg.value);

    try {
      switch (msg.command) {
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
