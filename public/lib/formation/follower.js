(function () {
  const Commands = window.GeoFsCommands;

  function buildFollowerCommands(config, leaderTelemetry, followerTelemetry) {
    if (!leaderTelemetry || !followerTelemetry) return [];

    const headingRad = Number.isFinite(Number(leaderTelemetry.heading_rad))
      ? Number(leaderTelemetry.heading_rad)
      : config.startPose.heading_rad;
    const altitudeM = Number.isFinite(Number(leaderTelemetry.altitude_m))
      ? Number(leaderTelemetry.altitude_m)
      : config.startPose.altitude_m;
    const speedMps = Number.isFinite(Number(leaderTelemetry.speed_mps))
      ? Number(leaderTelemetry.speed_mps)
      : config.startPose.speed_mps;

    return [
      Commands.autopilotEnable(),
      Commands.autopilotTargets({
        heading_rad: headingRad,
        altitude_m: altitudeM,
        speed_mps: speedMps,
      }),
    ];
  }

  window.GeoFsFormation = {
    ...(window.GeoFsFormation || {}),
    buildFollowerCommands,
  };
})();
