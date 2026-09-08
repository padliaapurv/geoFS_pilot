#!/usr/bin/env python3
"""End-to-end confirmation of the real fix, using the actual (fixed)
js/wake/core.js as shipped -- not the inline hand-rolled sequence from
probe27. Select the aircraft, inject core.js, call GeoFSWake.commandTrim()
exactly as a real user/README would, and watch 40s of flight for a stable,
non-stalling, altitude/speed-holding trim with no manual engine/velocity
workarounds from the test script itself.
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

result = driver.execute_script("""
    return window.GeoFSWake.commandTrim({ cl: 0.5, altitudeFt: 10000, headingDeg: 90 })
        .then(trim => ({ ok: true, trim }))
        .catch(err => ({ ok: false, error: String(err) }));
""")
print('commandTrim result:', json.dumps(result, indent=1))

driver.save_screenshot('/home/apurv/geofstmp/geoFS_pilot/test/shot_fixed_trim_start.png')

for i in range(20):
    time.sleep(2)
    f = driver.execute_script("return window.GeoFSWake.flightState();")
    av = driver.execute_script("return { thrust: window.geofs.animation.values.thrust, speedBug: window.geofs.autopilot.values.speed, engineOn: window.controls.engine.on };")
    print(f"t={i*2}s thr={f['throttle']:.2f} eng={av['engineOn']} thrust={av['thrust']:.0f} speedBug={av['speedBug']:.1f} kias={f['kias']:.1f} altFt={f['altitudeFt']:.0f} vs={f['verticalSpeedFpm']:.0f} pitch={f['pitchDeg']:.1f} aoa={f.get('aoaDeg')}")

driver.save_screenshot('/home/apurv/geofstmp/geoFS_pilot/test/shot_fixed_trim_end.png')
driver.quit()
