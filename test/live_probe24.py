#!/usr/bin/env python3
"""Isolate whether W.placeAircraft's teleport actually imparts the requested
forward velocity, or leaves the aircraft essentially stationary (a "falling
brick") right after being teleported to 10000ft -- which would explain the
huge AoA/pitch oscillations seen in probe23 even with the autopilot ordering
and throttle both fixed. Autopilot and engines OFF here: just teleport and
watch raw kias/altitude/pitch at high time resolution.
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

print('gear/flaps before:', driver.execute_script("return { gearPosition: window.geofs.animation.values.gearPosition, flapsPosition: window.geofs.animation.values.flapsPosition, groundContact: window.geofs.animation.values.groundContact };"))

r = driver.execute_script("""
    const W = window.GeoFSWake;
    return W.waitForGeoFS().then(() => {
        const f = W.flightState();
        const massKg = W.aircraftMassKg();
        const altitudeFt = 10000;
        const altitudeM = altitudeFt * W.constants.FT_TO_M;
        const headingDeg = 90;
        const tasMps = W.trimTasMps(massKg, altitudeM, 0.5);
        const ok = W.placeAircraft({ latDeg: f.latDeg, lonDeg: f.lonDeg, altitudeM, headingDeg }, tasMps);
        return { ok, tasMps, before: f };
    });
""")
print('placeAircraft call:', json.dumps(r, indent=1))

for i in range(12):
    time.sleep(0.25)
    f = driver.execute_script("return window.GeoFSWake.flightState();")
    tas = driver.execute_script("return window.geofs.aircraft.instance.trueAirSpeed;")
    print(f"t={i*0.25:.2f}s kias={f['kias']} tas={tas} altFt={f['altitudeFt']:.0f} vs={f['verticalSpeedFpm']} pitch={f['pitchDeg']} aoa={f.get('aoaDeg')}")
driver.quit()
