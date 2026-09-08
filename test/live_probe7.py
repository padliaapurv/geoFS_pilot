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

    for b in driver.find_elements(By.TAG_NAME, 'button'):
        if b.text.strip().lower() == 'consent':
            driver.execute_script("arguments[0].click();", b)
            break
    time.sleep(2)

    fly = driver.find_element(By.CSS_SELECTOR, '.geofs-fly-button')
    print('fly displayed:', fly.is_displayed())
    driver.execute_script("arguments[0].click();", fly)
    print('clicked FLY')
    time.sleep(6)
    driver.save_screenshot('/home/apurv/geofstmp/geoFS_pilot/test/shot3_after_fly.png')

    for i in range(30):
        has_aircraft = driver.execute_script("return !!(window.geofs && window.geofs.aircraft && window.geofs.aircraft.instance);")
        if has_aircraft:
            print(f'[t={i}s] hasAircraft=True')
            break
        time.sleep(1)
    else:
        print('aircraft never appeared after FLY click')

    name = driver.execute_script("""
        const a = window.geofs?.aircraft?.instance;
        return a ? (a.definition?.name || a.aircraftRecord?.name || a.name || 'unknown') : null;
    """)
    print('Aircraft name:', name)
    driver.save_screenshot('/home/apurv/geofstmp/geoFS_pilot/test/shot4_flying.png')
finally:
    driver.quit()
