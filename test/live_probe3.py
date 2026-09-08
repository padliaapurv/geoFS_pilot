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

try:
    driver.get('https://www.geo-fs.com/geofs.php')
    time.sleep(15)

    fly = driver.find_element(By.CSS_SELECTOR, '.geofs-fly-button')
    driver.execute_script("arguments[0].click();", fly)
    print('Clicked FLY! (via JS)')
    time.sleep(6)

    for i in range(30):
        has_aircraft = driver.execute_script("return !!(window.geofs && window.geofs.aircraft && window.geofs.aircraft.instance);")
        print(f'[t={i}s] hasAircraft={has_aircraft}')
        if has_aircraft:
            break
        time.sleep(1)

    name = driver.execute_script("""
        const a = window.geofs?.aircraft?.instance;
        return a ? (a.definition?.name || a.aircraftRecord?.name || a.name || 'unknown') : null;
    """)
    print('Aircraft name:', name)

    # Look for an aircraft-selection UI (usually reachable via a menu button).
    ui_dump = driver.execute_script("""
        return Array.from(document.querySelectorAll('a, div.control-pad, div[class*=menu], div[class*=aircraft]'))
            .filter(el => el.offsetParent !== null)
            .map(el => ({ tag: el.tagName, cls: el.className, text: (el.innerText||'').slice(0,40) }))
            .slice(0, 60);
    """)
    print(json.dumps(ui_dump, indent=1))
finally:
    driver.quit()
