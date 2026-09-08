#!/usr/bin/env python3
"""controls.throttle reads back 0 immediately even right after being set to
0.85 (probe16): something in GeoFS's per-frame loop resets it from raw input
state. Dump the actual source of controls.update / updateKeyboard / the
throttle axis setter to find the real persistent write path (axisSetters,
controls.states, or a key-hold simulation), instead of guessing further.
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

info = driver.execute_script("""
    return {
      axisSettersKeys: Object.keys(window.controls.axisSetters || {}),
      statesKeys: Object.keys(window.controls.states || {}),
      states: window.controls.states,
      updateSrc: (window.controls.update || '').toString().slice(0, 4000),
    };
""")
print('axisSettersKeys:', info['axisSettersKeys'])
print('statesKeys:', info['statesKeys'])
print('states:', json.dumps(info['states'], indent=1, default=str))
print('--- update() source (first 4000 chars) ---')
print(info['updateSrc'])
driver.quit()
