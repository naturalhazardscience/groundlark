"""Framework smoke check: real HTTP page construction and static model delivery.

Run in the locked UI environment. Browser interaction checks are documented
separately; this check deliberately does not claim to exercise WebGL.
"""
from pathlib import Path
import base64
import html
import socket
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from urllib.error import URLError
from urllib.request import urlopen


def main():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("main.py")), "--port", str(port)],
                                   stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    with urlopen(f"http://127.0.0.1:{port}/", timeout=3) as response:
                        page = html.unescape(response.read().decode())
                    break
                except URLError:
                    if time.monotonic() >= deadline or process.poll() is not None:
                        log.seek(0)
                        raise RuntimeError(log.read().decode(errors="replace"))
                    time.sleep(.1)
            for text in ("Groundlark", "STIMULUS LAB", "Finish &amp; save", "Pose &amp; vibration"):
                # NiceGUI encodes element text as JSON instead of HTML entities.
                assert text.replace("&amp;", "&") in page, text
            assert "IMU 3" in page and "IMU 4" not in page, "Current workbench must expose exactly three IMUs"
            assert 'SCL3300' not in page and 'Inclinometer' not in page, 'Removed sensor must not be advertised'
            assert 'nominal 25.4' in page, 'Missing geophone visualization description'
            with urlopen(f"http://127.0.0.1:{port}/board-assets/daqhat-01.glb", timeout=10) as response:
                assert response.read(4) == b"glTF"
            assert 'GNSS timing' in page and 'MAX-M10S' in page and 'Apply GNSS signals' in page
            assert 'Antenna fault stimulus' in page and 'Shorted' in page
            assert 'Test selected board' in page and 'Skylark USB' in page
            assert 'Air quality stimulus' in page and 'The FPGA is not required for sensor experiments.' in page
            assert 'Enclosure climate' in page and 'SHT45' in page
            assert all(f'Magnetometer {i}' in page for i in range(1,5)), 'B1 requires four separate magnetic views'
            with urlopen(f"http://127.0.0.1:{port}/station",timeout=3) as response:
                station_page=html.unescape(response.read().decode())
            assert 'Station configuration' in station_page and 'Download SSREC' in station_page
            assert 'Simulation and replay' in station_page
            with urlopen(f"http://127.0.0.1:{port}/board-assets/burrowlark.glb", timeout=10) as response:
                assert response.read(4) == b'glTF'
            with urlopen(f"http://127.0.0.1:{port}/board-assets/skylark.glb", timeout=10) as response:
                assert response.read(4) == b'glTF'
            assert 'href="/favicon.ico"' in page
            with urlopen(f"http://127.0.0.1:{port}/favicon.ico", timeout=3) as response:
                icon = response.read()
                assert response.headers.get_content_type().startswith("image/")
            assert icon[:4] == b"\x00\x00\x01\x00", "Expected a browser ICO asset"
            assert icon == (Path(__file__).parent / "assets/groundlark-favicon.ico").read_bytes()
            assert '/board-assets/groundlark-wordmark.svg' in page, 'Missing shared header wordmark'
            with urlopen(f"http://127.0.0.1:{port}/board-assets/groundlark-wordmark.svg", timeout=3) as response:
                assert response.headers.get_content_type() == 'image/svg+xml'
                wordmark = response.read()
                assert wordmark == (Path(__file__).parent / 'assets/groundlark-wordmark.svg').read_bytes()
            mark = ET.fromstring(wordmark).find('{http://www.w3.org/2000/svg}image')
            source = mark.attrib['{http://www.w3.org/1999/xlink}href']
            assert base64.b64decode(source.split(',', 1)[1]) == (Path(__file__).parent / 'assets/groundlark-icon.png').read_bytes()
            print("PASS workbench HTTP page, KiCad GLB, shared wordmark and favicon delivery")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
