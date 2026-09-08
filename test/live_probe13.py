#!/usr/bin/env python3
"""Introspect GeoFS's real controls/throttle API to find the correct write path.

live_probe12 showed that setting window.controls.throttle = 0.85 does not
stick: throttle read back as 0.00 for the full 40s window while the aircraft
stalled and dove. Hypothesis: GeoFS's main loop recomputes controls.throttle
every frame from raw input state (keys/axes), overwriting any one-shot write.
This probe dumps the shape of window.controls and related objects to find
the actual input-state field or a dedicated setter.
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
    function shape(o, depth) {
      if (!o || typeof o !== 'object' || depth <= 0) return typeof o;
      const out = {};
      for (const k of Object.keys(o)) {
        try {
          const v = o[k];
          if (typeof v === 'function') out[k] = 'function';
          else if (v && typeof v === 'object') out[k] = shape(v, depth - 1);
          else out[k] = v;
        } catch (e) { out[k] = 'ERR:' + e; }
      }
      return out;
    }
    return {
      controlsKeys: Object.keys(window.controls || {}),
      controlsShape: shape(window.controls, 2),
      hasSetters: !!(window.controls && window.controls.setters),
      settersKeys: Object.keys((window.controls && window.controls.setters) || {}),
      animationValuesKeys: Object.keys((window.geofs && window.geofs.animation && window.geofs.animation.values) || {}),
      throttleRelatedTopLevel: Object.keys(window.geofs || {}).filter(k => /throttle|thrust|engine|power/i.test(k)),
    };
""")
print(json.dumps(info, indent=1, default=str))
driver.quit()
