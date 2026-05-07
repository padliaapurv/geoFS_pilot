(function () {
  function autopilotEnable() {
    return { command: 'autopilot_enable' };
  }

  function autopilotDisable() {
    return { command: 'autopilot_disable' };
  }

  function autopilotTargets({ heading_rad, altitude_m, speed_mps } = {}) {
    return {
      command: 'autopilot_targets',
      targets: { heading_rad, altitude_m, speed_mps },
    };
  }

  function resetPose({ lat_rad, lon_rad, altitude_m, heading_rad, speed_mps } = {}) {
    return {
      command: 'reset_pose',
      pose: { lat_rad, lon_rad, altitude_m, heading_rad, speed_mps },
    };
  }

  function directControls({ roll, pitch, yaw, throttle } = {}) {
    return {
      command: 'controls_set',
      controls: { roll, pitch, yaw, throttle },
    };
  }

  function controlsNeutral() {
    return { command: 'controls_neutral' };
  }

  function discrete(action, value) {
    return { command: 'discrete', action, value };
  }

  window.GeoFsCommands = {
    autopilotEnable,
    autopilotDisable,
    autopilotTargets,
    resetPose,
    directControls,
    controlsNeutral,
    discrete,
    gearToggle: () => discrete('gearToggle'),
    gearUp: () => discrete('gearUp'),
    gearDown: () => discrete('gearDown'),
    flapsUp: () => discrete('flapsUp'),
    flapsDown: () => discrete('flapsDown'),
    flapsCycle: () => discrete('flapsCycle'),
    brakesOn: () => discrete('brakesOn'),
    brakesOff: () => discrete('brakesOff'),
    parkingBrakeToggle: () => discrete('parkingBrakeToggle'),
    enginesToggle: () => discrete('enginesToggle'),
    airbrakesToggle: () => discrete('airbrakesToggle'),
    airbrakesFull: () => discrete('airbrakesFull'),
    airbrakesRetract: () => discrete('airbrakesRetract'),
    trimUp: () => discrete('trimUp'),
    trimDown: () => discrete('trimDown'),
    trimNeutral: () => discrete('trimNeutral'),
  };
})();
