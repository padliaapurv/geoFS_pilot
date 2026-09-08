#!/usr/bin/env python3
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

# Close any open menu overlay so it doesn't intercept anything, then inject the real wake-sim sources.
driver.execute_script("document.body.click();")
time.sleep(1)

core_js = open('js/wake/core.js').read()
driver.execute_script(core_js)
print('injected core.js')

result = driver.execute_script("""
    return window.GeoFSWake.commandTrim({ cl: 0.5, altitudeFt: 10000, headingDeg: 90 })
        .then(trim => ({ ok: true, trim }))
        .catch(err => ({ ok: false, error: String(err) }));
""")
print('commandTrim result:', json.dumps(result, indent=1))

time.sleep(2)
state = driver.execute_script("""
    const ap = window.geofs.autopilot;
    const f = window.GeoFSWake.flightState();
    return { autopilotOn: ap.on, autopilotMode: ap.mode, apValues: ap.values, flight: f };
""")
print('post-trim state:', json.dumps(state, indent=1, default=str))
driver.save_screenshot('/home/apurv/geofstmp/geoFS_pilot/test/shot_after_trim.png')
driver.quit()
