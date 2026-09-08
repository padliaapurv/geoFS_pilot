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
    driver.save_screenshot('/home/apurv/geofstmp/geoFS_pilot/test/shot1_loaded.png')
    print('saved shot1')

    fly = driver.find_element(By.CSS_SELECTOR, '.geofs-fly-button')
    print('fly button displayed:', fly.is_displayed(), 'rect:', fly.rect)
finally:
    driver.quit()
