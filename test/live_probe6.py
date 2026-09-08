#!/usr/bin/env python3
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

    # Click the cookie-consent "Consent" button by visible text.
    buttons = driver.find_elements(By.TAG_NAME, 'button')
    clicked = False
    for b in buttons:
        if b.text.strip().lower() == 'consent':
            driver.execute_script("arguments[0].click();", b)
            clicked = True
            print('Clicked Consent button')
            break
    if not clicked:
        print('Consent button not found by text; dumping all buttons:')
        for b in buttons:
            print(' -', repr(b.text))

    time.sleep(3)
    driver.save_screenshot('/home/apurv/geofstmp/geoFS_pilot/test/shot2_after_consent.png')
    print('saved shot2')
finally:
    driver.quit()
