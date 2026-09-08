#!/usr/bin/env python3
"""probe29 showed the follower diverging from its target position at a rate
matching roughly the aircraft's own cruise speed -- suspiciously large.
Hypothesis: this is a Selenium test-harness artifact, not a real bug.
switch_to.new_window('tab') put both aircraft in ONE OS window with only one
tab visible at a time; browsers throttle timers (setInterval, rAF) in
hidden/background tabs, so the leader's 100ms state-broadcast timer would
have stalled while its tab was backgrounded, leaving the follower's control
loop comparing its own fresh position against a stale, real-seconds-old
leader position -- which would look exactly like a divergence at ~the
aircraft's own airspeed. Test with two separate top-level windows instead
(closer to the README's real documented usage: two visible GeoFS windows),
checking document.hidden in both throughout, for a shorter 20s run.
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

print('leader hidden:', driver.execute_script("return document.hidden;", ) if False else None)
driver.switch_to.window(leader_handle)
print('leader tab document.hidden:', driver.execute_script("return document.hidden;"))
driver.switch_to.window(follower_handle)
print('follower tab document.hidden:', driver.execute_script("return document.hidden;"))

driver.switch_to.window(leader_handle)
r = driver.execute_script("""
    return window.geofsWake.startLeader({ cl: 0.5, altitudeFt: 10000, headingDeg: 90, massKg: 250000, session: 'probe30' })
        .then(s => ({ ok: true }))
        .catch(err => ({ ok: false, error: String(err) }));
""")
print('startLeader:', r)
print('leader tab document.hidden (after start):', driver.execute_script("return document.hidden;"))

time.sleep(2)

driver.switch_to.window(follower_handle)
r = driver.execute_script("""
    return window.geofsWake.startFollower({ cl: 0.5, massKg: 250000, targetDownstreamM: 300, initialCrossM: 0, initialVerticalM: 0, mode: 'hold', session: 'probe30' })
        .then(s => ({ ok: true }))
        .catch(err => ({ ok: false, error: String(err) }));
""")
print('startFollower:', r)
print('follower tab document.hidden (after start):', driver.execute_script("return document.hidden;"))

for i in range(8):
    time.sleep(2.5)
    driver.switch_to.window(leader_handle)
    lhidden = driver.execute_script("return document.hidden;")
    lf = driver.execute_script("return window.GeoFSWake.flightState();")
    driver.switch_to.window(follower_handle)
    fhidden = driver.execute_script("return document.hidden;")
    ff = driver.execute_script("return window.GeoFSWake.flightState();")
    fs = driver.execute_script("return window.geofsWake.status();")
    leaderAgeMs = fs.get('leaderAgeMs')
    rel = fs.get('relative') or {}
    print(
        f"t={i*2.5:.1f}s leaderHidden={lhidden} followerHidden={fhidden} leaderAgeMs={leaderAgeMs} | "
        f"LEAD kias={lf['kias']:.1f} altFt={lf['altitudeFt']:.0f} | "
        f"FOLLOW kias={ff['kias']:.1f} altFt={ff['altitudeFt']:.0f} | "
        f"rel downstream={rel.get('downstreamM')} cross={rel.get('crossM')}"
    )

driver.quit()
