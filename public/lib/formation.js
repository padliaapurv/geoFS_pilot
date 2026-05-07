(function () {
  const {
    bearingDeg,
    distanceNm,
    hasPosition,
    normalizeHeading,
    offsetPositionByNm,
    shortestHeadingDelta,
  } = window.GeoFsGeo;

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function wakeFromLeaderToFollower(_leaderTelemetry, _followerTelemetry) {
    return null;
  }

  function injectWakeIntoFollowerCommand(followerCommand, _wakeModel) {
    return followerCommand;
  }

  function buildFollowerCommand(config, leaderTelemetry, followerTelemetry) {
    if (!hasPosition(leaderTelemetry) || !hasPosition(followerTelemetry)) return null;

    const leaderHeading = normalizeHeading(
      leaderTelemetry.heading_deg || config.startPose.heading_deg
    );
    const targetPosition = offsetPositionByNm(
      leaderTelemetry,
      leaderHeading + 180,
      config.desiredSpacingNm
    );
    const spacing = distanceNm(leaderTelemetry, followerTelemetry);
    const rangeToTarget = distanceNm(followerTelemetry, targetPosition) || 0;
    const headingToTarget = bearingDeg(followerTelemetry, targetPosition);
    if (headingToTarget == null) return null;

    const closure = clamp(
      rangeToTarget * config.gains.closureKtsPerNm,
      0,
      config.gains.maxClosureKts
    );
    const leaderSpeed = Number(leaderTelemetry.speed_kts) || config.startPose.speed_kts;
    const targetSpeed =
      spacing != null && spacing < config.desiredSpacingNm * 0.5
        ? Math.max(90, leaderSpeed - config.gains.maxClosureKts)
        : leaderSpeed + closure;
    const headingError = shortestHeadingDelta(followerTelemetry.heading_deg || 0, headingToTarget);
    const altitudeError =
      (Number(leaderTelemetry.altitude_ft) || config.startPose.altitude_ft) -
      (Number(followerTelemetry.altitude_ft) || config.startPose.altitude_ft);
    const speedError = targetSpeed - (Number(followerTelemetry.speed_kts) || targetSpeed);
    const throttleBase =
      Number.isFinite(Number(followerTelemetry.throttle))
        ? Number(followerTelemetry.throttle)
        : 0.65;

    return {
      controls: {
        roll: clamp(headingError / 35, -0.8, 0.8),
        pitch: clamp(altitudeError / 1500, -0.4, 0.4),
        yaw: 0,
        throttle: clamp(throttleBase + speedError / 120, 0, 1),
      },
      target_spacing_nm: config.desiredSpacingNm,
      current_spacing_nm: spacing,
      heading_error_deg: headingError,
    };
  }

  window.GeoFsFormation = {
    wakeFromLeaderToFollower,
    injectWakeIntoFollowerCommand,
    buildFollowerCommand,
  };
})();
