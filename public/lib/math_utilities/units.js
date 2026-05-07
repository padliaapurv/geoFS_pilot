(function () {
  const METERS_PER_FOOT = 0.3048;
  const METERS_PER_NAUTICAL_MILE = 1852;
  const METERS_PER_SECOND_PER_KNOT = 0.514444;

  function degreesToRadians(degrees) {
    return (Number(degrees) * Math.PI) / 180;
  }

  function radiansToDegrees(radians) {
    return (Number(radians) * 180) / Math.PI;
  }

  function feetToMeters(feet) {
    return Number(feet) * METERS_PER_FOOT;
  }

  function metersToFeet(meters) {
    return Number(meters) / METERS_PER_FOOT;
  }

  function nauticalMilesToMeters(nauticalMiles) {
    return Number(nauticalMiles) * METERS_PER_NAUTICAL_MILE;
  }

  function metersToNauticalMiles(meters) {
    return Number(meters) / METERS_PER_NAUTICAL_MILE;
  }

  function knotsToMetersPerSecond(knots) {
    return Number(knots) * METERS_PER_SECOND_PER_KNOT;
  }

  function metersPerSecondToKnots(metersPerSecond) {
    return Number(metersPerSecond) / METERS_PER_SECOND_PER_KNOT;
  }

  window.GeoFsUnits = {
    METERS_PER_FOOT,
    METERS_PER_NAUTICAL_MILE,
    METERS_PER_SECOND_PER_KNOT,
    degreesToRadians,
    radiansToDegrees,
    feetToMeters,
    metersToFeet,
    nauticalMilesToMeters,
    metersToNauticalMiles,
    knotsToMetersPerSecond,
    metersPerSecondToKnots,
  };
})();
