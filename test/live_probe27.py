#!/usr/bin/env python3
"""Full corrected sequence test, inline (not yet in core.js):
  1. engines on
  2. a.place(lla, htr) to teleport to altitude/heading (as before)
  3. directly set a.rigidBody.v_linearVelocity to the ENU vector for the
     desired TAS/heading (fixing the "falling brick" bug from probe24/25/26)
  4. enableAutopilot() (turnOn) FIRST
  5. setAutopilotTargets() AFTER (fixing the bug-clobbering from probe21/22)
Then watch 40s of flight for a stable, non-stalling trim.
"""
import json
import time
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By

options = Options()
options.binary_location = '/snap/firefox/current/usr/lib/firefox/firefox'
service = Service(executable_path='/snap/bin/geckodriver')
driver = webdriver.Firefox(options=options, service=service)
driver.set_page_load_timeout(60)
driver.set_window_size(1400, 900)
driver.get('https://www.geo-fs.com/geofs.php')
time.sleep(15)
for b in driver.find_elements(By.TAG_NAME, 'button'):
    if b.text.strip().lower() == 'consent':
        driver.execute_script('arguments[0].click();', b)
        break
time.sleep(3)
for candidate in driver.find_elements(By.CSS_SELECTOR, '.geofs-fly-button'):
    if candidate.is_displayed():
        candidate.click()
        break
time.sleep(4)
for b in driver.find_elements(By.TAG_NAME, 'button'):
    if b.text.strip().upper() == 'AIRCRAFT':
        b.click()
        break
time.sleep(2)
for el in driver.find_elements(By.TAG_NAME, 'li'):
    if el.text.strip() == 'Boeing 777-300ER' and el.is_displayed():
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        break
time.sleep(2)
for el in driver.find_elements(By.XPATH, "//*[contains(text(), 'White Tail')]"):
    if el.is_displayed():
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        break
time.sleep(6)
driver.execute_script("document.body.click();")
time.sleep(1)

core_js = open('js/wake/core.js').read()
driver.execute_script(core_js)
driver.execute_script("window.controls.engine.on = true;")

typeinfo = driver.execute_script("""
    const rb = window.geofs.aircraft.instance.rigidBody;
    return { isArray: Array.isArray(rb.v_linearVelocity), ctor: rb.v_linearVelocity.constructor.name, len: rb.v_linearVelocity.length };
""")
print('v_linearVelocity type info:', typeinfo)

result = driver.execute_script("""
    const W = window.GeoFSWake;
    return W.waitForGeoFS().then(() => {
        const f = W.flightState();
        const massKg = W.aircraftMassKg();
        const altitudeFt = 10000;
        const altitudeM = altitudeFt * W.constants.FT_TO_M;
        const headingDeg = 90;
        const cl = 0.5;
        const tasMps = W.trimTasMps(massKg, altitudeM, cl);
        const speedKias = W.trimKias(massKg, cl);
        const a = window.geofs.aircraft.instance;
        a.place([f.latDeg, f.lonDeg, altitudeM], [headingDeg, 0, 0]);
        const hRad = headingDeg * Math.PI / 180;
        const east = tasMps * Math.sin(hRad);
        const north = tasMps * Math.cos(hRad);
        const rb = a.rigidBody;
        rb.v_linearVelocity[0] = east;
        rb.v_linearVelocity[1] = north;
        rb.v_linearVelocity[2] = 0;
        return new Promise((resolve) => window.setTimeout(() => {
            W.enableAutopilot();
            W.setAutopilotTargets({ headingDeg, altitudeFt, speedKias });
            resolve({ speedKias, altitudeFt, headingDeg, east, north, tasMps });
        }, 100));
    });
""")
print('trim setup result:', json.dumps(result, indent=1))

for i in range(20):
    time.sleep(2)
    f = driver.execute_script("return window.GeoFSWake.flightState();")
    av = driver.execute_script("return { thrust: window.geofs.animation.values.thrust, speedBug: window.geofs.autopilot.values.speed };")
    print(f"t={i*2}s thr={f['throttle']:.2f} thrust={av['thrust']:.0f} speedBug={av['speedBug']:.1f} kias={f['kias']:.1f} altFt={f['altitudeFt']:.0f} vs={f['verticalSpeedFpm']:.0f} pitch={f['pitchDeg']:.1f} aoa={f.get('aoaDeg')}")
driver.quit()
