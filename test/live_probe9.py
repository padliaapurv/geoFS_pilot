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

# Click AIRCRAFT in the bottom toolbar.
aircraft_btn = None
for el in driver.find_elements(By.CSS_SELECTOR, 'div, a, li'):
    if el.text.strip().upper() == 'AIRCRAFT' and el.is_displayed():
        aircraft_btn = el
        break
print('aircraft button found:', aircraft_btn is not None)
if aircraft_btn:
    aircraft_btn.click()
    time.sleep(2)
    driver.save_screenshot('/home/apurv/geofstmp/geoFS_pilot/test/shot_aircraft_menu.png')

    # Dump the menu structure to find how to search/select the 777-200.
    dump = driver.execute_script("""
        return Array.from(document.querySelectorAll('input, div[class*=aircraft], div[class*=list], li'))
            .filter(el => el.offsetParent !== null)
            .slice(0, 60)
            .map(el => ({tag: el.tagName, cls: el.className, text: (el.innerText||'').slice(0,40), placeholder: el.placeholder || null}));
    """)
    print(json.dumps(dump, indent=1))

driver.quit()
