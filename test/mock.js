'use strict';
// Minimal browser-global mock + loader for the geofs_wake_sim modules.
// Each call to createSandbox() builds a fresh, isolated global context
// (via vm.createContext) so tests never leak state through window.GeoFSWake.

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const WAKE_DIR = path.join(__dirname, '..', 'js', 'wake');
const FILES = ['core.js', 'field.js', 'seeker.js', 'runtime.js'];

function makeMockGeofs({ aircraft = true } = {}) {
  const values = {
    heading360: 90,
    atilt: 0,
    aroll: 0,
    kias: 250,
    ktas: 260,
    altitude: 10000,
    verticalSpeed: 0,
    aoa: 2,
    loadFactor: 1,
  };
  const instance = aircraft ? {
    llaLocation: [37.6, -122.3, 3048],
    definition: { name: 'Boeing 777-200' },
    rigidBody: { mass: 200000 },
  } : null;

  const autopilotCalls = [];
  const autopilot = {
    setCourse: (v) => { autopilotCalls.push(['setCourse', v]); autopilot._heading = v; },
    setAltitude: (v) => { autopilotCalls.push(['setAltitude', v]); autopilot._altitude = v; },
    setSpeedMode: (v) => { autopilotCalls.push(['setSpeedMode', v]); },
    setSpeed: (v) => { autopilotCalls.push(['setSpeed', v]); autopilot._speed = v; },
    turnOn: () => { autopilotCalls.push(['turnOn']); autopilot.on = true; },
    on: false,
    _calls: autopilotCalls,
  };

  return {
    aircraft: { instance },
    animation: { values },
    autopilot,
    api: {},
  };
}

function makeMockWeather() {
  return {
    currentWindVector: [0, 0, 0],
    currentWindSpeedMs: 0,
    currentWindSpeed: 0,
    currentWindDirection: 0,
    windActive: false,
    update() { return 'orig-update'; },
  };
}

/**
 * Build an isolated sandbox with window/geofs/controls/weather mocked,
 * then load core/field/seeker/runtime.js into it in order.
 * Returns { sandbox, W } where W === sandbox.window.GeoFSWake.
 */
function createSandbox(opts = {}) {
  const sandbox = {};
  sandbox.window = sandbox; // window === global-in-sandbox, matches browser semantics well enough
  sandbox.console = console;
  sandbox.Math = Math;
  sandbox.Date = Date;
  sandbox.performance = performance;
  sandbox.BroadcastChannel = BroadcastChannel;
  sandbox.setTimeout = setTimeout;
  sandbox.setInterval = setInterval;
  sandbox.clearInterval = clearInterval;
  sandbox.Number = Number;
  sandbox.Array = Array;
  sandbox.Object = Object;
  sandbox.Promise = Promise;
  sandbox.String = String;
  sandbox.Error = Error;

  sandbox.geofs = makeMockGeofs(opts.geofs);
  sandbox.controls = { throttle: 0.6 };
  sandbox.weather = makeMockWeather();

  vm.createContext(sandbox);

  for (const file of FILES) {
    const code = fs.readFileSync(path.join(WAKE_DIR, file), 'utf8');
    vm.runInContext(code, sandbox, { filename: file });
  }

  return { sandbox, W: sandbox.GeoFSWake };
}

module.exports = { createSandbox, makeMockGeofs, makeMockWeather };
