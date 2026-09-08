#!/usr/bin/env python3
"""probe21: after commandTrim (which calls setSpeed(291) then enableAutopilot
-> turnOn()), ap.values.speed ended up ~7.3 (matching current kias), not 291.
Hypothesis: ap.turnOn() (or UI init) captures the CURRENT speed as the bug
when engaging, overwriting whatever setSpeed() set beforehand. Dump
ap.turnOn/toggle source to confirm, then test calling setSpeed AFTER turnOn
instead of before.
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
    return { turnOnSrc: ap.turnOn.toString(), toggleSrc: ap.toggle.toString(), initSrc: ap.init.toString().slice(0, 1500) };
""")
print('--- turnOn ---')
print(info['turnOnSrc'])
print('--- toggle ---')
print(info['toggleSrc'])
print('--- init (first 1500 chars) ---')
print(info['initSrc'])

# Now test: engine on, then turnOn autopilot FIRST, then setSpeed/setCourse/setAltitude AFTER.
driver.execute_script("window.controls.engine.on = true;")
r = driver.execute_script("""
    const ap = window.geofs.autopilot;
    ap.turnOn();
    ap.setCourse(90);
    ap.setAltitude(10000);
    ap.setSpeedMode('knots');
    ap.setSpeed(291);
    return { on: ap.on, speedBug: ap.values.speed, altBug: ap.values.altitude, courseBug: ap.values.course };
""")
print('after turnOn-then-set:', r)
time.sleep(1)
r2 = driver.execute_script("return { speedBug: window.geofs.autopilot.values.speed };")
print('1s later, speedBug:', r2)
driver.quit()
