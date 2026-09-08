#!/usr/bin/env python3
"""probe20 found ap.update() DOES run a real autothrottle PID every frame:
  a.PIDs.throttle.set(x, 0, 1); controls.throttle = a.PIDs.throttle.compute(S, e)
where x = a.values.speed (the KIAS bug) and S = current kias. This should
drive throttle toward 1 given the huge speed error we observed (target ~291,
actual ~18-94). But observed throttle stayed exactly 0. Check whether
ap.values.speed (the bug) actually got set to our target by setSpeed, and
dump the PID class's compute()/set() source and internal state/gains to
find why it outputs 0 despite a large positive speed error.
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
    return window.GeoFSWake.commandTrim({ cl: 0.5, altitudeFt: 10000, headingDeg: 90 })
        .then(trim => ({ ok: true, trim }))
        .catch(err => ({ ok: false, error: String(err) }));
""")
print('commandTrim result:', json.dumps(result, indent=1))

info = driver.execute_script("""
    const ap = window.geofs.autopilot;
    const pid = ap.PIDs.throttle;
    return {
      valuesSpeed: ap.values.speed,
      speedMode: ap.speedMode,
      currentKias: window.geofs.animation.values.kias,
      pidKeys: Object.keys(pid),
      pidState: JSON.parse(JSON.stringify(pid, (k, v) => typeof v === 'function' ? 'function' : v)),
      pidSetSrc: pid.set.toString(),
      pidComputeSrc: pid.compute.toString(),
    };
""")
print(json.dumps(info, indent=1, default=str))
driver.quit()
