#!/usr/bin/env python3
"""probe24 proved W.placeAircraft's speed argument is ignored: the aircraft
free-falls from rest after teleport (v = g*t exactly). Dump the real
signatures/sources of geofs.api.setAircraftPosition and
aircraft.instance.setPosition/place to find how to actually impart forward
velocity on placement (a velocity vector? a separate call? rigidBody state?).
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
    const api = window.geofs.api || {};
    const a = window.geofs.aircraft.instance;
    function safeSrc(fn) { try { return fn.toString().slice(0, 3000); } catch (e) { return 'ERR:' + e; } }
    return {
      apiKeys: Object.keys(api),
      setAircraftPositionSrc: typeof api.setAircraftPosition === 'function' ? safeSrc(api.setAircraftPosition) : typeof api.setAircraftPosition,
      instanceSetPositionSrc: typeof a.setPosition === 'function' ? safeSrc(a.setPosition) : typeof a.setPosition,
      instancePlaceSrc: typeof a.place === 'function' ? safeSrc(a.place) : typeof a.place,
      rigidBodyKeys: Object.keys(a.rigidBody || {}),
      instanceKeysVel: Object.keys(a).filter(k => /vel|speed/i.test(k)),
    };
""")
print(json.dumps(info, indent=1, default=str))
driver.quit()
