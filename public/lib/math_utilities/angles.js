(function () {
  const TWO_PI = Math.PI * 2;

  function normalizeAngleRad(radians) {
    return ((Number(radians) % TWO_PI) + TWO_PI) % TWO_PI;
  }

  function shortestAngleDeltaRad(fromRad, toRad) {
    return normalizeAngleRad(toRad - fromRad + Math.PI) - Math.PI;
  }

  window.GeoFsAngles = {
    TWO_PI,
    normalizeAngleRad,
    shortestAngleDeltaRad,
  };
})();
