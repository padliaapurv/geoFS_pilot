// ==UserScript==
// @name         GeoFS geoBridge API
// @namespace    geofs_pilot
// @version      1.0.0
// @description  Safe browser-side telemetry and control bridge for GeoFS.
// @match        https://www.geo-fs.com/geofs.php*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  const TAG = '[geoBridge]';
  const READY_POLL_MS = 250;
  const BRIDGE_FLAG = '__geoBridgeWrappedByScript';

  function isReady() {
    return !!(
      window.geofs &&
      window.geofs.aircraft?.instance &&
      window.geofs.animation?.values &&
      window.controls &&
      typeof window.geofs.api?.addFrameCallback === 'function'
    );
  }

  function waitForReady() {
    return new Promise((resolve) => {
      const tick = () => {
        if (isReady()) {
          resolve(true);
          return;
        }
        setTimeout(tick, READY_POLL_MS);
      };
      tick();
    });
  }

  const state = {
    installed: false,
    ready: false,
    keyListenerInstalled: false,
    keyListener: null,
    frameCallback: null,
    frameCallbackId: null,
    originalUpdate: null,
    appliedCount: 0,
    lastBefore: null,
    lastAfter: null,
    lastTime: null,
    cmd: { roll: 0, pitch: 0, yaw: 0, throttle: null },
  };

  const clamp = (v, min, max) => Math.max(min, Math.min(max, v));
  const num = (v, fallback = 0) => (Number.isFinite(Number(v)) ? Number(v) : fallback);

  function readTelemetry() {
    const g = window.geofs;
    const a = g?.aircraft?.instance;
    const av = g?.animation?.values;
    const c = window.controls;
    const rb = a?.rigidBody;
    const lla = a?.lla || null;
    const htr = a?.htr || [av?.heading360 ?? null, av?.atilt ?? null, av?.aroll ?? null];
    const velocityENU = a?.veldir || a?.velocity || null;

    return {
      time: Date.now(),
      lla,
      htr,
      velocityENU,
      speedMS: num(a?.trueAirSpeed ?? a?.groundSpeed ?? 0),
      velocityDir: a?.veldir || null,
      rbLinearVelocityENU: rb?.v || rb?.velocity || null,
      rbAngularVelocity: rb?.w || null,
      rbAcceleration: rb?.a || null,
      rbAngularAcceleration: rb?.aw || null,
      rbJerk: rb?.j || null,
      rbMass: num(rb?.mass, null),
      headingDeg: num(av?.heading360, null),
      tiltDeg: num(av?.atilt, null),
      rollDeg: num(av?.aroll, null),
      altitudeMeters: num(lla?.[2], null),
      altitudeFeet: num(av?.altitude, null),
      haglMeters: num(av?.hagl, null),
      kias: num(av?.kias, null),
      ktas: num(av?.ktas, null),
      airspeedMS: num(av?.ktas, null) * 0.514444,
      groundSpeedMS: num(av?.groundSpeed, null),
      groundSpeedKnt: num(av?.groundSpeedKnt ?? av?.groundSpeed, null),
      verticalSpeedFPM: num(av?.verticalSpeed, null),
      aoaDeg: num(av?.aoa, null),
      loadFactor: num(av?.loadFactor, null),
      throttle: num(c?.throttle, null),
      brakes: num(c?.brakes, null),
      gearPosition: num(av?.gearPosition ?? a?.gearPosition, null),
      flapsPosition: num(av?.flapsPosition ?? c?.flaps?.position, null),
      stalling: !!av?.stalling,
      crashed: !!a?.crashed,
      groundContact: !!a?.groundContact,
    };
  }

  function snapshotControls() {
    const c = window.controls || {};
    return {
      roll: num(c.roll, 0),
      rawPitch: num(c.rawPitch, 0),
      pitch: num(c.pitch, 0),
      yaw: num(c.yaw, 0),
      throttle: num(c.throttle, 0),
      elevatorTrim: num(c.elevatorTrim, 0),
    };
  }

  function applyCmd(cmd) {
    const c = window.controls;
    if (!c) return;
    c.roll = cmd.roll;
    c.rawPitch = cmd.pitch;
    c.yaw = cmd.yaw;
    c.pitch = c.rawPitch + (c.elevatorTrim || 0);
    if (cmd.throttle !== null) c.throttle = cmd.throttle;
  }

  function installUpdateWrapper() {
    const c = window.controls;
    if (!c || typeof c.update !== 'function') return false;

    if (c.update && c.update[BRIDGE_FLAG]) {
      state.originalUpdate = c.update.__geoBridgeOriginal || state.originalUpdate;
      return true;
    }

    state.originalUpdate = c.update;

    // Risky integration point:
    // We wrap GeoFS controls.update, call original first, then post-override
    // only when geoBridge continuous control mode is enabled.
    const wrapped = function geoBridgeWrappedUpdate(e) {
      const result = state.originalUpdate.call(this, e);
      if (window.geoBridge?.controls?.enabled) {
        state.lastBefore = snapshotControls();
        applyCmd(state.cmd);
        state.lastAfter = snapshotControls();
        state.lastTime = Date.now();
        state.appliedCount += 1;
      }
      return result;
    };

    wrapped[BRIDGE_FLAG] = true;
    wrapped.__geoBridgeOriginal = state.originalUpdate;
    c.update = wrapped;
    return true;
  }

  function uninstallUpdateWrapper() {
    const c = window.controls;
    if (c && state.originalUpdate && c.update && c.update[BRIDGE_FLAG]) {
      c.update = state.originalUpdate;
      return true;
    }
    return false;
  }

  function installKeyListener() {
    if (state.keyListenerInstalled) return;
    state.keyListener = (ev) => {
      if (ev.repeat) return;
      const target = ev.target;
      const tag = target?.tagName;
      const editable = !!target?.isContentEditable;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || editable) return;
      if (String(ev.key || '').toLowerCase() !== 'y') return;
      const enabled = geoBridge.controls.toggle();
      console.log(`${TAG} override ${enabled ? 'enabled' : 'disabled'}`);
    };
    window.addEventListener('keydown', state.keyListener, { capture: true });
    state.keyListenerInstalled = true;
  }

  function uninstallKeyListener() {
    if (!state.keyListenerInstalled || !state.keyListener) return;
    window.removeEventListener('keydown', state.keyListener, { capture: true });
    state.keyListenerInstalled = false;
    state.keyListener = null;
  }

  function callSetter(name, ...args) {
    const s = window.controls?.setters;
    if (s && typeof s[name] === 'function') {
      const out = s[name](...args);
      return { ok: true, action: name, via: 'setters', result: out ?? null };
    }
    return { ok: false, action: name, via: 'missing_setter' };
  }

  const geoBridge = {
    telemetry: { read: () => readTelemetry() },
    controls: {
      enabled: false,
      enable() {
        this.enabled = true;
        window.geofs?.autopilot?.turnOff?.();
        return this.enabled;
      },
      disable() {
        this.enabled = false;
        return this.enabled;
      },
      toggle() {
        return this.enabled ? this.disable() : this.enable();
      },
      neutral() {
        state.cmd.roll = 0;
        state.cmd.pitch = 0;
        state.cmd.yaw = 0;
        state.cmd.throttle = null;
        return { ok: true, cmd: { ...state.cmd } };
      },
      set(cmd = {}) {
        if ('roll' in cmd) state.cmd.roll = clamp(num(cmd.roll, 0), -1, 1);
        if ('pitch' in cmd) state.cmd.pitch = clamp(num(cmd.pitch, 0), -1, 1);
        if ('yaw' in cmd) state.cmd.yaw = clamp(num(cmd.yaw, 0), -1, 1);
        if ('throttle' in cmd) {
          state.cmd.throttle = cmd.throttle === null ? null : clamp(num(cmd.throttle, 0), 0, 1);
        }
        return { ok: true, cmd: { ...state.cmd } };
      },
      snapshot() {
        return snapshotControls();
      },
    },
    discrete: {
      gearToggle: () => callSetter('setGearToggle'),
      gearUp: () => callSetter('setGear', 0),
      gearDown: () => callSetter('setGear', 1),
      flapsUp: () => callSetter('setFlapsUp'),
      flapsDown: () => callSetter('setFlapsDown'),
      flapsCycle: () => callSetter('cycleFlaps'),
      brakesOn: () => callSetter('setBrakes', 1),
      brakesOff: () => callSetter('setBrakes', 0),
      parkingBrakeToggle: () => callSetter('setParkingBrakeToggle'),
      enginesToggle: () => callSetter('setEngineOn'),
      autopilotToggle: () => callSetter('setAutoPilot'),
      airbrakesToggle: () => callSetter('setAirbrakesToggle'),
      airbrakesFull: () => callSetter('setAirbrakes', 1),
      airbrakesRetract: () => callSetter('setAirbrakes', 0),
      trimUp: () => callSetter('trimUp'),
      trimDown: () => callSetter('trimDown'),
      trimNeutral: () => callSetter('trimZero'),
    },
    debug: {
      status() {
        return {
          ready: state.ready,
          installed: state.installed,
          controlsEnabled: geoBridge.controls.enabled,
          appliedCount: state.appliedCount,
          lastBefore: state.lastBefore,
          lastAfter: state.lastAfter,
          telemetry: geoBridge.telemetry.read(),
          hasOriginalControlsUpdate: !!state.originalUpdate,
          hasKeyListener: state.keyListenerInstalled,
        };
      },
    },
    lifecycle: {
      async install() {
        await waitForReady();
        state.ready = true;
        installUpdateWrapper();
        installKeyListener();
        if (!state.frameCallback && window.geofs?.api?.addFrameCallback) {
          state.frameCallback = () => {
            state.lastTime = Date.now();
          };
          state.frameCallbackId = window.geofs.api.addFrameCallback(state.frameCallback);
        }
        state.installed = true;
        return true;
      },
      uninstall() {
        geoBridge.controls.disable();
        uninstallKeyListener();
        uninstallUpdateWrapper();
        if (state.frameCallbackId != null) {
          window.geofs?.api?.removeFrameCallback?.(state.frameCallbackId);
        }
        state.frameCallback = null;
        state.frameCallbackId = null;
        state.installed = false;
        delete window.geoBridge;
        return true;
      },
      isInstalled() {
        return state.installed;
      },
    },
  };

  window.geoBridge = geoBridge;
  geoBridge.lifecycle.install();
})();
