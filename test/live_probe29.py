#!/usr/bin/env python3
"""End-to-end two-aircraft leader/follower test, the actual purpose of this
repo (commandTrim alone was already confirmed fixed in probe28). Opens two
tabs in the same Firefox profile (so BroadcastChannel works between them),
selects the Boeing 777-300ER in both, injects the full runtime
(core+field+seeker+runtime, matching js/geofs_wake_sim.user.js's @require
order), starts the leader in tab 1 and the follower in tab 2, and watches
both for a stable, non-stalling flight with real wake injection and
guidance corrections for ~40s.
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

RUNTIME_JS = '\n'.join(
    open(f'js/wake/{name}').read()
    for name in ('core.js', 'field.js', 'seeker.js', 'runtime.js')
)


def load_and_select_aircraft():
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


# Tab 1: leader.
load_and_select_aircraft()
leader_handle = driver.current_window_handle

# Tab 2: follower.
driver.switch_to.new_window('tab')
load_and_select_aircraft()
follower_handle = driver.current_window_handle

driver.switch_to.window(leader_handle)
r = driver.execute_script("""
    return window.geofsWake.startLeader({ cl: 0.5, altitudeFt: 10000, headingDeg: 90, massKg: 250000, session: 'probe29' })
        .then(s => ({ ok: true, s }))
        .catch(err => ({ ok: false, error: String(err) }));
""")
print('startLeader:', json.dumps(r, indent=1, default=str)[:800])

time.sleep(2)

driver.switch_to.window(follower_handle)
r = driver.execute_script("""
    return window.geofsWake.startFollower({ cl: 0.5, massKg: 250000, targetDownstreamM: 300, initialCrossM: 0, initialVerticalM: 0, mode: 'hold', session: 'probe29' })
        .then(s => ({ ok: true, s }))
        .catch(err => ({ ok: false, error: String(err) }));
""")
print('startFollower:', json.dumps(r, indent=1, default=str)[:1500])

for i in range(16):
    time.sleep(2.5)
    driver.switch_to.window(leader_handle)
    lf = driver.execute_script("return window.GeoFSWake.flightState();")
    driver.switch_to.window(follower_handle)
    ff = driver.execute_script("return window.GeoFSWake.flightState();")
    fs = driver.execute_script("return window.geofsWake.status();")
    rel = fs.get('relative') or {}
    wake = fs.get('wake') or {}
    print(
        f"t={i*2.5:.1f}s "
        f"LEAD kias={lf['kias']:.1f} altFt={lf['altitudeFt']:.0f} pitch={lf['pitchDeg']:.1f} | "
        f"FOLLOW kias={ff['kias']:.1f} altFt={ff['altitudeFt']:.0f} pitch={ff['pitchDeg']:.1f} aoa={ff.get('aoaDeg')} thr={ff['throttle']:.2f} | "
        f"rel downstream={rel.get('downstreamM')} cross={rel.get('crossM')} vert={rel.get('verticalM')} | "
        f"wake u={wake.get('uMps')} v={wake.get('vMps')} w={wake.get('wMps')}"
    )

driver.switch_to.window(follower_handle)
driver.save_screenshot('/home/apurv/geofstmp/geoFS_pilot/test/shot_follower_end.png')
driver.switch_to.window(leader_handle)
driver.save_screenshot('/home/apurv/geofstmp/geoFS_pilot/test/shot_leader_end.png')

driver.quit()
