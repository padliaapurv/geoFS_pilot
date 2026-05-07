(function () {
  function finiteNumber(...values) {
    for (const value of values) {
      if (value == null || value === '') continue;
      const number = Number(value);
      if (Number.isFinite(number)) return number;
    }
    return null;
  }

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  window.GeoFsMath = {
    ...(window.GeoFsMath || {}),
    finiteNumber,
    clamp,
  };
})();
