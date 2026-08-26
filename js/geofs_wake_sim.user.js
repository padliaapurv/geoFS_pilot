// ==UserScript==
// @name         GeoFS Boeing 777 Wake Simulation
// @namespace    geofs_wake
// @version      2.0.0
// @description  Inject a local 3-D wake field into GeoFS and run Boeing 777-200 wake-following tests.
// @match        https://www.geo-fs.com/geofs.php*
// @require      https://raw.githubusercontent.com/padliaapurv/geoFS_pilot/main/js/wake/core.js
// @require      https://raw.githubusercontent.com/padliaapurv/geoFS_pilot/main/js/wake/field.js
// @require      https://raw.githubusercontent.com/padliaapurv/geoFS_pilot/main/js/wake/seeker.js
// @require      https://raw.githubusercontent.com/padliaapurv/geoFS_pilot/main/js/wake/runtime.js
// @grant        none
// @run-at       document-idle
// ==/UserScript==

console.log('[geofsWake] userscript loaded. Open two GeoFS tabs and run leader/follower commands from the console.');
