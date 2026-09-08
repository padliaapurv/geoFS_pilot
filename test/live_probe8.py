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

def refocus_firefox():
    win_ids = subprocess.run(['xdotool', 'search', '--name', 'Mozilla Firefox'],
                              env={'DISPLAY': ':1'}, capture_output=True, text=True).stdout.split()
    if win_ids:
        wid = win_ids[-1]
        subprocess.run(['xdotool', 'windowraise', wid], env={'DISPLAY': ':1'})
        subprocess.run(['xdotool', 'windowactivate', '--sync', wid], env={'DISPLAY': ':1'})
        subprocess.run(['xdotool', 'windowfocus', '--sync', wid], env={'DISPLAY': ':1'})
        time.sleep(0.5)

def real_click_element(el):
    refocus_firefox()
    rect = driver.execute_script(
        "const r = arguments[0].getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height};", el)
    win_pos = driver.get_window_position()
    chrome_y = driver.execute_script("return window.outerHeight - window.innerHeight;")
    chrome_x = driver.execute_script("return window.outerWidth - window.innerWidth;")
    screen_x = int(win_pos['x'] + chrome_x + rect['x'] + rect['w'] / 2)
    screen_y = int(win_pos['y'] + chrome_y + rect['y'] + rect['h'] / 2)
    print(f'  rect={rect} -> screen click at ({screen_x},{screen_y})')
    subprocess.run(['xdotool', 'mousemove', str(screen_x), str(screen_y)], env={'DISPLAY': ':1'}, check=True)
    time.sleep(0.2)
    subprocess.run(['xdotool', 'click', '1'], env={'DISPLAY': ':1'}, check=True)

try:
    driver.get('https://www.geo-fs.com/geofs.php')
    time.sleep(15)

    win_ids = subprocess.run(['xdotool', 'search', '--name', 'Mozilla Firefox'],
                              env={'DISPLAY': ':1'}, capture_output=True, text=True).stdout.split()
    print('firefox window ids:', win_ids)
    if win_ids:
        wid = win_ids[-1]
        subprocess.run(['xdotool', 'windowraise', wid], env={'DISPLAY': ':1'})
        subprocess.run(['xdotool', 'windowactivate', '--sync', wid], env={'DISPLAY': ':1'})
        subprocess.run(['xdotool', 'windowfocus', '--sync', wid], env={'DISPLAY': ':1'})
        time.sleep(1)
    active = subprocess.run(['xdotool', 'getactivewindow', 'getwindowname'],
                             env={'DISPLAY': ':1'}, capture_output=True, text=True).stdout.strip()
    print('active window is now:', active)

    for b in driver.find_elements(By.TAG_NAME, 'button'):
        if b.text.strip().lower() == 'consent':
            driver.execute_script("arguments[0].click();", b)
            print('dismissed consent (JS click)')
            break
    fly = None
    for i in range(20):
        time.sleep(1)
        for candidate in driver.find_elements(By.CSS_SELECTOR, '.geofs-fly-button'):
            if candidate.is_displayed() and candidate.size['width'] > 0:
                fly = candidate
                break
        if fly:
            print(f'fly button became visible after {i+1}s')
            break
    if fly is None:
        print('fly button never became visible/sized')
        driver.save_screenshot('/home/apurv/geofstmp/geoFS_pilot/test/shot5b_timeout.png')
        raise SystemExit(1)
    print('real-clicking FLY button')
    real_click_element(fly)
    time.sleep(6)
    driver.save_screenshot('/home/apurv/geofstmp/geoFS_pilot/test/shot5_after_real_fly_click.png')

    for i in range(30):
        has_aircraft = driver.execute_script("return !!(window.geofs && window.geofs.aircraft && window.geofs.aircraft.instance);")
        if has_aircraft:
            print(f'[t={i}s] hasAircraft=True')
            break
        time.sleep(1)
    else:
        print('aircraft never appeared after real FLY click')

    name = driver.execute_script("""
        const a = window.geofs?.aircraft?.instance;
        return a ? (a.definition?.name || a.aircraftRecord?.name || a.name || 'unknown') : null;
    """)
    print('Aircraft name:', name)
    driver.save_screenshot('/home/apurv/geofstmp/geoFS_pilot/test/shot6_flying.png')
finally:
    driver.quit()
