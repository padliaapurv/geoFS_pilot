#!/usr/bin/env python3
"""probe18: with autopilot OFF and no repositioning, throttle=0.85 sticks and
thrust ramps up fine. probe16 set throttle BEFORE commandTrim (which
repositions the aircraft via placeAircraft, since it starts below 2000ft) --
so the reposition may be what zeroes it, a one-time reset, not a continuous
autopilot override. Isolate: run full commandTrim (reposition + autopilot
on), let it finish, THEN set throttle, and watch whether it sticks with the
autopilot engaged.
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
print('commandTrim result (throttle untouched by us):', json.dumps(result, indent=1))
print('post-trim ap state:', driver.execute_script("return { apOn: window.geofs.autopilot.on, throttle: window.controls.throttle, altFt: window.geofs.animation.values.altitude };"))

print('Now setting throttle=0.85 AFTER trim, with autopilot still on:')
driver.execute_script("window.controls.throttle = 0.85;")
for i in range(10):
    time.sleep(0.5)
    r = driver.execute_script("return { throttle: window.controls.throttle, apOn: window.geofs.autopilot.on, thrust: window.geofs.animation.values.thrust, kias: window.geofs.animation.values.kias, altFt: window.geofs.animation.values.altitude };")
    print(f"t={i*0.5:.1f}s", r)
driver.quit()
