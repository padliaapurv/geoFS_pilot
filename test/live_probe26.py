#!/usr/bin/env python3
"""probe25: a.place(lla, htr) only sets position/orientation, never velocity
-- that's the entire bug. Real physics velocity lives at
a.rigidBody.v_linearVelocity. Inspect its shape/units, check for a
top-level `a.velocity` alias, and check whether window.Cesium is exposed
globally (GeoFS is Cesium-based) so we can build an ENU->fixed-frame
rotation to convert a desired (heading, TAS) into that vector's frame.
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

# Start engines and throttle up on the runway to get some real, known motion,
# so we can see how v_linearVelocity relates to heading/speed while taxiing.
driver.execute_script("window.controls.engine.on = true; window.controls.throttle = 1; window.controls.brakes = 0; window.controls.parkingBrake = false;")
time.sleep(5)

info = driver.execute_script("""
    const a = window.geofs.aircraft.instance;
    const rb = a.rigidBody;
    return {
      hasCesium: typeof window.Cesium,
      velocityType: typeof a.velocity,
      velocity: a.velocity,
      vLinVelType: typeof rb.v_linearVelocity,
      vLinVel: rb.v_linearVelocity,
      llaLocation: a.llaLocation,
      heading: window.geofs.animation.values.heading360,
      groundSpeed: a.groundSpeed,
      trueAirSpeed: a.trueAirSpeed,
      airVelocity: a.airVelocity,
      velocityDirection: a.velocityDirection,
      utilsKeys: Object.keys(window.geofs.utils || {}),
    };
""")
print(json.dumps(info, indent=1, default=str))
driver.quit()
