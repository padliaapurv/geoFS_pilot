#!/usr/bin/env python3
"""Verify the real fix hypothesis end to end, inline (not yet in core.js):
  1. start engines (controls.engine.on = true)
  2. reposition/set altitude as commandTrim does
  3. enableAutopilot() (turnOn) FIRST
  4. setAutopilotTargets() AFTER, so turnOn's self-capture doesn't clobber it
Then watch 40s of flight to confirm speed converges toward the trim target,
altitude holds near 10000ft, and there is no stall/dive.
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

result = driver.execute_script("""
    return window.GeoFSWake.waitForGeoFS().then(() => {
        const W = window.GeoFSWake;
        const f = W.flightState();
        const massKg = W.aircraftMassKg();
        const cl = 0.5;
        const altitudeFt = 10000;
        const headingDeg = 90;
        const altitudeM = altitudeFt * W.constants.FT_TO_M;
        const tasMps = W.trimTasMps(massKg, altitudeM, cl);
        const speedKias = W.trimKias(massKg, cl);
        if (f.altitudeFt < 2000 && f.latDeg != null) {
            W.placeAircraft({ latDeg: f.latDeg, lonDeg: f.lonDeg, altitudeM, headingDeg }, tasMps);
        }
        return new Promise((resolve) => window.setTimeout(() => {
            W.enableAutopilot();
            W.setAutopilotTargets({ headingDeg, altitudeFt, speedKias });
            resolve({ speedKias, altitudeFt, headingDeg, apValuesSpeed: window.geofs.autopilot.values.speed });
        }, 400));
    });
""")
print('trim setup result:', json.dumps(result, indent=1))

for i in range(20):
    time.sleep(2)
    f = driver.execute_script("return window.GeoFSWake.flightState();")
    av = driver.execute_script("return { thrust: window.geofs.animation.values.thrust, speedBug: window.geofs.autopilot.values.speed, apOn: window.geofs.autopilot.on };")
    print(f"t={i*2}s thr={f['throttle']:.2f} thrust={av['thrust']:.0f} speedBug={av['speedBug']:.1f} kias={f['kias']:.1f} altFt={f['altitudeFt']:.0f} vs={f['verticalSpeedFpm']:.0f} pitch={f['pitchDeg']:.1f} aoa={f.get('aoaDeg')}")
driver.quit()
