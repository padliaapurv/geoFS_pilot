#!/usr/bin/env python3
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
driver.set_window_size(1400, 900)

try:
    driver.get('https://www.geo-fs.com/geofs.php')
    time.sleep(15)

    # Dump visible DOM structure to find menu/UI overlay elements.
    info = driver.execute_script("""
        function describe(el, depth) {
            if (!el || depth > 3) return null;
            const rect = el.getBoundingClientRect ? el.getBoundingClientRect() : null;
            return {
                tag: el.tagName,
                id: el.id || null,
                cls: (el.className && typeof el.className === 'string') ? el.className : null,
                text: (el.innerText || '').slice(0, 40),
                visible: rect ? (rect.width > 0 && rect.height > 0) : null,
            };
        }
        const all = Array.from(document.querySelectorAll('div, button, a, canvas'))
            .filter(el => el.offsetParent !== null || el.tagName === 'CANVAS')
            .slice(0, 80)
            .map(el => describe(el, 0));
        return all;
    """)
    print(json.dumps(info, indent=1))
finally:
    driver.quit()
