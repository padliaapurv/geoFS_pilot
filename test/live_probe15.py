#!/usr/bin/env python3
"""Find the real way to start engines in GeoFS.

probe14 showed controls.setters.toggleEngines is listed as a key but is not
actually a callable function at runtime. Inspect setter types and try
directly flipping controls.engine.on, plus look for a keyboard-binding table
mapping a real key (e.g. Shift+E in stock GeoFS) to engine start.
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
    const setterTypes = {};
    for (const k of Object.keys(window.controls.setters || {})) {
      setterTypes[k] = typeof window.controls.setters[k];
    }
    let keyBindings = null;
    try {
      keyBindings = window.geofs.keyboardShortcuts || window.geofs.keyMap || window.keyMap || null;
    } catch (e) {}
    return {
      setterTypes,
      engineKeys: Object.keys(window.controls.engine || {}),
      engineShape: window.controls.engine,
      aircraftInstanceEngineKeys: Object.keys(window.geofs.aircraft.instance || {}).filter(k => /engine/i.test(k)),
      definitionEngineInfo: (window.geofs.aircraft.instance.definition || {}).engines || null,
      hasKeyMapGlobal: typeof window.keyMap,
      geofsKeys: Object.keys(window.geofs).filter(k => /key|shortcut|bind/i.test(k)),
    };
""")
print(json.dumps(info, indent=1, default=str))

# Try direct property flip.
r2 = driver.execute_script("""
    window.controls.engine.on = true;
    return { on: window.controls.engine.on };
""")
print('after direct set engine.on=true:', r2)
time.sleep(2)
r3 = driver.execute_script("return { on: window.controls.engine.on, thrust: window.geofs.animation.values.thrust, rpm: window.geofs.animation.values.rpm };")
print('2s later:', r3)
driver.quit()
