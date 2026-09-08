#!/usr/bin/env python3
"""Live probe against the real GeoFS site to check the actual geofs.* API
surface that js/wake/core.js assumes. Not part of the automated test suite
(needs network + a real browser); run manually for validation."""
import json
import time
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

options = Options()
options.binary_location = '/snap/firefox/current/usr/lib/firefox/firefox'
service = Service(executable_path='/snap/bin/geckodriver')
driver = webdriver.Firefox(options=options, service=service)
driver.set_page_load_timeout(60)

try:
    driver.get('https://www.geo-fs.com/geofs.php')

    # Poll for window.geofs to exist at all (should appear quickly, before
    # any aircraft is even spawned).
    for i in range(40):
        has_geofs = driver.execute_script("return typeof window.geofs !== 'undefined';")
        if has_geofs:
            print(f'[t={i}s] window.geofs exists')
            break
        time.sleep(1)
    else:
        print('window.geofs never appeared after 40s')
        driver.quit()
        raise SystemExit(1)

    # Poll for an aircraft instance (may need a default aircraft to auto-spawn,
    # or may require UI interaction -- report what we find either way).
    for i in range(60):
        state = driver.execute_script("""
            const g = window.geofs;
            return {
                hasAircraft: !!(g && g.aircraft && g.aircraft.instance),
                hasAnimationValues: !!(g && g.animation && g.animation.values),
                hasControls: typeof window.controls !== 'undefined',
                hasAutopilot: !!(g && g.autopilot),
                hasWeather: typeof window.weather !== 'undefined',
            };
        """)
        print(f'[t={i}s]', state)
        if state['hasAircraft'] and state['hasAutopilot']:
            break
        time.sleep(1)

    dump = driver.execute_script("""
        const g = window.geofs;
        function safeKeys(obj) {
            if (!obj) return null;
            const out = [];
            for (const k in obj) {
                try { out.push(k + ':' + typeof obj[k]); } catch (e) { out.push(k + ':ERR'); }
            }
            return out;
        }
        return {
            aircraftInstanceKeys: g?.aircraft?.instance ? safeKeys(g.aircraft.instance).slice(0, 60) : null,
            autopilotKeys: g?.autopilot ? safeKeys(g.autopilot) : null,
            animationValuesKeys: g?.animation?.values ? safeKeys(g.animation.values) : null,
            weatherKeys: window.weather ? safeKeys(window.weather).slice(0, 40) : null,
            controlsKeys: window.controls ? safeKeys(window.controls) : null,
            aircraftName: g?.aircraft?.instance?.definition?.name || g?.aircraft?.instance?.aircraftRecord?.name || null,
        };
    """)
    print(json.dumps(dump, indent=2))

finally:
    driver.quit()
