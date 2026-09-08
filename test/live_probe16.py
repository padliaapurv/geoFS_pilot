#!/usr/bin/env python3
"""controls.setters entries are descriptor objects, not functions (probe15).
controls.engine.on = true works directly and rpm rose to 1000, but thrust
stayed 0 with throttle still 0. Inspect aircraft.instance.engine(s) shape,
then set engine.on = true AND throttle > 0, and watch whether thrust/kias
now develop normally, to confirm the full fix before touching core.js.
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

def shape(depth=1):
    return driver.execute_script("""
        function shape(o, depth) {
          if (!o || typeof o !== 'object' || depth <= 0) return Array.isArray(o) ? ('array[' + o.length + ']') : typeof o;
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
        const a = window.geofs.aircraft.instance;
        return { engine: shape(a.engine, %d), engines: shape(a.engines, %d) };
    """ % (depth, depth))

print('instance engine/engines shape:')
print(json.dumps(shape(2), indent=1, default=str))

core_js = open('js/wake/core.js').read()
driver.execute_script(core_js)

result = driver.execute_script("""
    window.controls.engine.on = true;
    window.controls.throttle = 0.85;
    return window.GeoFSWake.commandTrim({ cl: 0.5, altitudeFt: 10000, headingDeg: 90 })
        .then(trim => ({ ok: true, trim }))
        .catch(err => ({ ok: false, error: String(err) }));
""")
print('commandTrim result:', json.dumps(result, indent=1))

for i in range(20):
    time.sleep(2)
    f = driver.execute_script("return window.GeoFSWake.flightState();")
    av = driver.execute_script("return { thrust: window.geofs.animation.values.thrust, engineOn: window.controls.engine.on, rpm: window.geofs.animation.values.rpm, throttle: window.controls.throttle };")
    print(f"t={i*2}s thr={av['throttle']:.2f} engOn={av['engineOn']} thrust={av['thrust']} rpm={av['rpm']} kias={f['kias']:.1f} altFt={f['altitudeFt']:.0f} vs={f['verticalSpeedFpm']:.0f} pitch={f['pitchDeg']:.1f} aoa={f.get('aoaDeg')}")
driver.quit()
