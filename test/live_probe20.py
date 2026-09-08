#!/usr/bin/env python3
"""probe19 proves the GeoFS autopilot, once engaged (ap.on = true), forces
controls.throttle back to 0 every single frame -- our assignment right
before a 0.5s poll is already undone by t=0.0s. This is a continuous,
per-frame override, not a one-shot reset from repositioning. Need to find
GeoFS's real autothrottle knob: dump window.geofs.autopilot's keys, values,
and function sources to find how it decides throttle (a mode flag, a target
field, or a separate autothrottle toggle).
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
    const ap = window.geofs.autopilot;
    function shape(o, depth) {
      if (!o || typeof o !== 'object' || depth <= 0) return typeof o;
      const out = {};
      for (const k of Object.keys(o)) {
        try {
          const v = o[k];
          out[k] = typeof v === 'function' ? 'function' : (v && typeof v === 'object' ? shape(v, depth - 1) : v);
        } catch (e) { out[k] = 'ERR'; }
      }
      return out;
    }
    const fnNames = Object.keys(ap).filter(k => typeof ap[k] === 'function');
    const srcs = {};
    for (const k of fnNames) {
      if (/throttle|speed|thrust|update/i.test(k)) srcs[k] = ap[k].toString().slice(0, 2500);
    }
    return { keys: Object.keys(ap), shape: shape(ap, 2), fnNames, srcs };
""")
print('autopilot keys:', info['keys'])
print()
print('autopilot shape:')
print(json.dumps(info['shape'], indent=1, default=str))
print()
print('function names:', info['fnNames'])
print()
for k, v in info['srcs'].items():
    print(f'--- ap.{k} source ---')
    print(v)
    print()
driver.quit()
