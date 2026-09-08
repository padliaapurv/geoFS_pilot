#!/usr/bin/env python3
"""Confirm engines-off is the real root cause of the stall/dive seen in probe12.

probe13 found window.controls.engine = {on: false} even after selecting the
aircraft and clicking through the fly-in flow. Throttle alone can't produce
thrust with engines off. This probe starts the engines via
controls.setters.toggleEngines(), sets throttle, and watches whether thrust
and airspeed now behave.
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

before = driver.execute_script("return { engineOn: window.controls.engine.on, throttle: window.controls.throttle };")
print('before:', before)

core_js = open('js/wake/core.js').read()
driver.execute_script(core_js)

result = driver.execute_script("""
    if (!window.controls.engine.on) window.controls.setters.toggleEngines();
    return window.GeoFSWake.commandTrim({ cl: 0.5, altitudeFt: 10000, headingDeg: 90 })
        .then(trim => ({ ok: true, trim, engineOnAfterToggle: window.controls.engine.on }))
        .catch(err => ({ ok: false, error: String(err) }));
""")
print('commandTrim result:', json.dumps(result, indent=1))

for i in range(20):
    time.sleep(2)
    f = driver.execute_script("return window.GeoFSWake.flightState();")
    av = driver.execute_script("return { thrust: window.geofs.animation.values.thrust, engineOn: window.controls.engine.on, rpm: window.geofs.animation.values.rpm };")
    print(f"t={i*2}s thr={f['throttle']:.2f} engOn={av['engineOn']} thrust={av['thrust']} rpm={av['rpm']} kias={f['kias']:.1f} altFt={f['altitudeFt']:.0f} vs={f['verticalSpeedFpm']:.0f} pitch={f['pitchDeg']:.1f} aoa={f.get('aoaDeg')}")
driver.quit()
