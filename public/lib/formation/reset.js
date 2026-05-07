(function () {
  const { hasPosition, offsetPosition } = window.GeoFsGeodesy;
  const { normalizeAngleRad } = window.GeoFsAngles;
  const Commands = window.GeoFsCommands;

  function buildResetCommands(config, leaderTelemetry) {
    if (!hasPosition(leaderTelemetry)) return [];

    const heading = normalizeAngleRad(
      Number.isFinite(Number(leaderTelemetry.heading_rad))
        ? Number(leaderTelemetry.heading_rad)
        : config.startPose.heading_rad
    );
    const behindM = Number(config.resetOffset?.behind_m) || 1000;
    const rightM = Number(config.resetOffset?.right_m) || 100;
    const aboveM = Number(config.resetOffset?.above_m) || 100;
    const northM = -behindM * Math.cos(heading) + rightM * Math.cos(heading + Math.PI / 2);
    const eastM = -behindM * Math.sin(heading) + rightM * Math.sin(heading + Math.PI / 2);
    const distanceM = Math.hypot(northM, eastM);
    const bearingRad = Math.atan2(eastM, northM);
    const position = offsetPosition(leaderTelemetry, bearingRad, distanceM);
    const leaderAltitudeM =
      Number.isFinite(Number(leaderTelemetry.altitude_m))
        ? Number(leaderTelemetry.altitude_m)
        : config.startPose.altitude_m;
    const resetAltitudeM = leaderAltitudeM + aboveM;
    const speedMps =
      Number.isFinite(Number(leaderTelemetry.speed_mps))
        ? Number(leaderTelemetry.speed_mps)
        : config.startPose.speed_mps;

    return [
      Commands.resetPose({
        ...position,
        altitude_m: resetAltitudeM,
        heading_rad: heading,
        speed_mps: speedMps,
      }),
      Commands.autopilotEnable(),
      Commands.autopilotTargets({
        heading_rad: heading,
        altitude_m: leaderAltitudeM,
        speed_mps: speedMps,
      }),
    ];
  }

  window.GeoFsFormation = {
    ...(window.GeoFsFormation || {}),
    buildResetCommands,
  };
})();
