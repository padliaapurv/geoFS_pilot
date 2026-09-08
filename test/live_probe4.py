#!/usr/bin/env python3
import json
import subprocess
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
driver.set_window_position(0, 0)
driver.set_window_size(1400, 900)

def xdotool(*args):
    subprocess.run(['xdotool', *args], env={'DISPLAY': ':1'}, check=True)

try:
    driver.get('https://www.geo-fs.com/geofs.php')
    time.sleep(15)

    # Bring the Firefox window to the front / focus it before clicking.
    win_ids = subprocess.run(['xdotool', 'search', '--name', 'Mozilla Firefox'],
                              env={'DISPLAY': ':1'}, capture_output=True, text=True).stdout.split()
    print('firefox window ids:', win_ids)
    if win_ids:
        xdotool('windowactivate', win_ids[0])
        time.sleep(1)

    fly = driver.find_element(By.CSS_SELECTOR, '.geofs-fly-button')
    rect = driver.execute_script("const r = arguments[0].getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height};", fly)
    win_pos = driver.get_window_position()
    win_rect = driver.get_window_rect()
    print('button rect (viewport):', rect, 'window pos:', win_pos, 'window rect:', win_rect)

    # Firefox chrome (tab bar/toolbar) adds an offset above the viewport;
    # measure it via window.outerHeight - window.innerHeight.
    chrome_offset = driver.execute_script("return window.outerHeight - window.innerHeight;")
    chrome_offset_x = driver.execute_script("return window.outerWidth - window.innerWidth;")
    print('chrome offset y:', chrome_offset, 'x:', chrome_offset_x)

    screen_x = int(win_pos['x'] + chrome_offset_x / 2 + rect['x'] + rect['w'] / 2)
    screen_y = int(win_pos['y'] + chrome_offset + rect['y'] + rect['h'] / 2)
    print('clicking at screen coords:', screen_x, screen_y)

    xdotool('mousemove', str(screen_x), str(screen_y))
    time.sleep(0.3)
    xdotool('click', '1')
    print('Real xdotool click sent')
    time.sleep(6)

    for i in range(30):
        has_aircraft = driver.execute_script("return !!(window.geofs && window.geofs.aircraft && window.geofs.aircraft.instance);")
        if has_aircraft:
            print(f'[t={i}s] hasAircraft=True')
            break
        time.sleep(1)
    else:
        print('aircraft never appeared')

    name = driver.execute_script("""
        const a = window.geofs?.aircraft?.instance;
        return a ? (a.definition?.name || a.aircraftRecord?.name || a.name || 'unknown') : null;
    """)
    print('Aircraft name:', name)
finally:
    driver.quit()
