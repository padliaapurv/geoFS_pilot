#!/usr/bin/env python3
"""Isolate whether the autopilot (turned on by commandTrim) is the thing
resetting controls.throttle back to 0 every frame, independent of the
update()-loop math (which, read in probe17, should just clamp and preserve
controls.throttle - controls.reverse). Engines on + throttle set, but do NOT
touch the autopilot at all, and watch throttle over a few seconds.
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

print('mode/reverse before:', driver.execute_script("return { mode: window.controls.mode, reverse: window.controls.reverse, apOn: window.geofs.autopilot.on };"))

driver.execute_script("window.controls.engine.on = true; window.controls.throttle = 0.85;")
for i in range(8):
    time.sleep(0.5)
    r = driver.execute_script("return { throttle: window.controls.throttle, reverse: window.controls.reverse, apOn: window.geofs.autopilot.on, thrust: window.geofs.animation.values.thrust };")
    print(f"t={i*0.5:.1f}s", r)
driver.quit()
