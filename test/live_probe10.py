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

try:
    driver.find_element(By.CSS_SELECTOR, '.mdi-close, [class*=close]').click()
except Exception:
    pass
driver.execute_script("""
    document.querySelectorAll('*').forEach(el => {
        if ((el.innerText||'').includes('Privacy and cookie settings')) {
            const p = el.closest('div');
            if (p) p.style.display = 'none';
        }
    });
""")
time.sleep(1)

for el in driver.find_elements(By.TAG_NAME, 'li'):
    if el.text.strip() == 'Boeing 777-300ER' and el.is_displayed():
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print('clicked Boeing 777-300ER (expands liveries)')
        break
time.sleep(2)

for el in driver.find_elements(By.XPATH, "//*[contains(text(), 'White Tail')]"):
    if el.is_displayed():
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.5)
        el.click()
        print('clicked White Tail livery')
        break
time.sleep(6)

name = driver.execute_script("""
    const a = window.geofs?.aircraft?.instance;
    return a ? (a.definition?.name || a.aircraftRecord?.name || a.name || 'unknown') : null;
""")
print('Aircraft name:', name)

dump = driver.execute_script("""
    const a = window.geofs?.aircraft?.instance;
    const av = window.geofs?.animation?.values;
    function safeKeys(obj, limit) {
        if (!obj) return null;
        const out = [];
        for (const k in obj) { try { out.push(k + ':' + JSON.stringify(obj[k]).slice(0, 60)); } catch(e){} }
        return out.slice(0, limit || 200);
    }
    return {
        llaLocation: a?.llaLocation,
        lla: a?.lla,
        definitionKeys: safeKeys(a?.definition, 40),
        rigidBodyKeys: safeKeys(a?.rigidBody, 20),
        directMass: a?.mass,
        htr: a?.htr,
        animationValues: safeKeys(av, 40),
        controlsThrottle: window.controls?.throttle,
        weatherCurrentWindVector: window.weather?.currentWindVector,
    };
""")
print(json.dumps(dump, indent=1, default=str))
driver.save_screenshot('/home/apurv/geofstmp/geoFS_pilot/test/shot_777_loaded.png')
driver.quit()
