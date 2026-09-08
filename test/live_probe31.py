#!/usr/bin/env python3
"""probe30 confirmed 'hold' mode formation-following works correctly in real
GeoFS (two separate windows, stable ~250-270m downstream, small cross-track
error). 'seek' mode is the actual novel contribution of this repo (dithers
lateral/vertical position and climbs the measured objective via
W.updateSeeker) and has never been live-tested -- only checked offline
against a mocked objective. Run it live for ~50s and watch: neither aircraft
should stall, the seeker's dither should stay bounded, and the seeker
telemetry (centerX/centerY/gradientX/gradientY/objective) should evolve
without diverging or crashing.
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

RUNTIME_JS = '\n'.join(
    open(f'js/wake/{name}').read()
    for name in ('core.js', 'field.js', 'seeker.js', 'runtime.js')
)


def load_and_select_aircraft():
    driver.set_window_size(700, 900)
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
    driver.execute_script(RUNTIME_JS)


load_and_select_aircraft()
leader_handle = driver.current_window_handle

driver.switch_to.new_window('window')
load_and_select_aircraft()
follower_handle = driver.current_window_handle

driver.switch_to.window(leader_handle)
r = driver.execute_script("""
    return window.geofsWake.startLeader({ cl: 0.5, altitudeFt: 10000, headingDeg: 90, massKg: 250000, session: 'probe31' })
        .then(s => ({ ok: true }))
        .catch(err => ({ ok: false, error: String(err) }));
""")
print('startLeader:', r)

time.sleep(2)

driver.switch_to.window(follower_handle)
r = driver.execute_script("""
    return window.geofsWake.startFollower({ cl: 0.5, massKg: 250000, targetDownstreamM: 300, initialCrossM: 5, initialVerticalM: 2, mode: 'seek', session: 'probe31' })
        .then(s => ({ ok: true }))
        .catch(err => ({ ok: false, error: String(err) }));
""")
print('startFollower (seek mode):', r)

for i in range(20):
    time.sleep(2.5)
    driver.switch_to.window(leader_handle)
    lf = driver.execute_script("return window.GeoFSWake.flightState();")
    driver.switch_to.window(follower_handle)
    ff = driver.execute_script("return window.GeoFSWake.flightState();")
    fs = driver.execute_script("return window.geofsWake.status();")
    rel = fs.get('relative') or {}
    seeker = fs.get('seeker') or {}
    print(
        f"t={i*2.5:.1f}s "
        f"LEAD kias={lf['kias']:.1f} altFt={lf['altitudeFt']:.0f} | "
        f"FOLLOW kias={ff['kias']:.1f} altFt={ff['altitudeFt']:.0f} aoa={ff.get('aoaDeg')} pitch={ff['pitchDeg']:.1f} thr={ff['throttle']:.2f} | "
        f"rel downstream={rel.get('downstreamM')} cross={rel.get('crossM')} vert={rel.get('verticalM')} | "
        f"seeker centerX={seeker.get('centerX')} centerY={seeker.get('centerY')} "
        f"gradX={seeker.get('gradientX')} gradY={seeker.get('gradientY')} obj={seeker.get('objective')}"
    )

driver.switch_to.window(follower_handle)
driver.save_screenshot('/home/apurv/geofstmp/geoFS_pilot/test/shot_seek_follower_end.png')
driver.quit()
