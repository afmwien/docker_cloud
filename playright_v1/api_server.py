"""
FastAPI Server für die 3-Ebenen Bildsuche mit Desktop-Screenshot.

Endpunkte:
  POST /search          - Bildsuche starten (URL + Referenzbild)
  POST /screenshot      - Reiner Screenshot (ohne Bildvergleich)
  GET  /health          - Health-Check
  GET  /screenshots/{f} - Screenshots abrufen
"""

import sys
import os
import uuid
import time
import base64
import subprocess
import asyncio
import hmac
import logging
from datetime import datetime
from pathlib import Path
from io import BytesIO

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Security, Depends, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from PIL import Image
import imagehash
import requests as req

sys.path.insert(0, str(Path(__file__).parent / "src"))

from browser.stealth import apply_stealth_settings, get_stealth_context_options
from screenshot.xvfb_screenshot import capture_xvfb_desktop

# Logging-Konfiguration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("api_server")

app = FastAPI(title="Image Finder Desktop", version="1.0.0")

# CORS: Erlaubt Anfragen von anderen Domains
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API-Key Authentifizierung
API_KEY = os.environ.get("API_KEY", "")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)):
    """Prüft den API-Key. Wenn kein API_KEY gesetzt ist, ist alles erlaubt."""
    if not API_KEY:
        return  # Kein Key konfiguriert → alles erlaubt
    if not api_key or not hmac.compare_digest(api_key, API_KEY):
        raise HTTPException(status_code=403, detail="Ungültiger API-Key")

DISPLAY = os.environ.get("DISPLAY", ":99")
OUTPUT_DIR = Path("/app/output/screenshots")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Persistentes Browser-Profil (für Login-Sessions)
CHROME_PROFILE_DIR = Path("/app/data/chrome_profile")
CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

# Aktive Login-Sessions verwalten
_active_login_session = None  # Chromium-Prozess für manuelle Logins

# Thread-Lock für Screenshots (nur einer gleichzeitig)
import threading
_screenshot_lock = threading.Lock()

# Idle-Timeout: Container beendet sich nach 1 Stunde Inaktivität
IDLE_TIMEOUT_SECONDS = int(os.environ.get("IDLE_TIMEOUT", "3600"))
_last_activity = time.time()


async def _idle_watchdog():
    """Hintergrund-Task: beendet den Prozess nach IDLE_TIMEOUT_SECONDS Inaktivität."""
    while True:
        await asyncio.sleep(60)  # Jede Minute prüfen
        idle = time.time() - _last_activity
        if idle >= IDLE_TIMEOUT_SECONDS:
            print(f"Idle-Timeout ({IDLE_TIMEOUT_SECONDS}s) erreicht. Container fährt herunter.")
            os._exit(0)


@app.on_event("startup")
async def startup():
    asyncio.create_task(_idle_watchdog())


def _touch_activity():
    """Aktualisiert den letzten Aktivitäts-Zeitstempel."""
    global _last_activity
    _last_activity = time.time()


def _maximize_window(display: str):
    """Maximiert das aktive Fenster auf dem Xvfb-Desktop."""
    env = {**os.environ, "DISPLAY": display}
    try:
        # Warte bis ein Fenster sichtbar ist
        subprocess.run(
            ["xdotool", "search", "--onlyvisible", "--name", ".", "windowactivate", "--sync"],
            env=env, timeout=5, capture_output=True,
        )
        # Aktives Fenster finden und maximieren
        result = subprocess.run(
            ["xdotool", "getactivewindow"],
            env=env, timeout=5, capture_output=True, text=True,
        )
        if result.returncode == 0:
            wid = result.stdout.strip()
            # Fensterdekorationen entfernen und Vollbild auf dem gesamten Screen
            screen_w = os.environ.get("SCREEN_WIDTH", "1920")
            screen_h = os.environ.get("SCREEN_HEIGHT", "1080")
            subprocess.run(
                ["wmctrl", "-i", "-r", wid, "-b", "add,maximized_vert,maximized_horz"],
                env=env, timeout=5, capture_output=True,
            )
            subprocess.run(
                ["xdotool", "windowsize", wid, screen_w, screen_h],
                env=env, timeout=5, capture_output=True,
            )
            subprocess.run(
                ["xdotool", "windowmove", wid, "0", "0"],
                env=env, timeout=5, capture_output=True,
            )
    except Exception:
        pass


@app.get("/health")
async def health():
    _touch_activity()
    idle = int(time.time() - _last_activity)
    remaining = max(0, IDLE_TIMEOUT_SECONDS - idle)
    return {
        "status": "healthy",
        "display": DISPLAY,
        "idle_timeout": IDLE_TIMEOUT_SECONDS,
        "remaining_seconds": remaining,
    }


def _run_search(url: str, ref_data: bytes, threshold: int, job_id: str) -> dict:
    """Synchrone Bildsuche – läuft in separatem Thread."""
    from playwright.sync_api import sync_playwright

    ref_img = Image.open(BytesIO(ref_data))
    ref_hash = imagehash.phash(ref_img.convert("RGB"), hash_size=16)
    print(f"Referenzbild: format={ref_img.format} size={ref_img.size} mode={ref_img.mode}")

    with sync_playwright() as p:
        # ---- PHASE 1: Headless Crawl + Bilder via Browser-Kontext laden ----
        browser_hl = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx_hl = browser_hl.new_context(**get_stealth_context_options())
        page_hl = ctx_hl.new_page()
        apply_stealth_settings(page_hl)

        # Response-Interceptor: Bilddaten aus dem Netzwerk abfangen
        captured_images = {}

        def _on_response(response):
            try:
                ct = response.headers.get("content-type", "")
                if "image" in ct and response.status == 200:
                    body = response.body()
                    if len(body) > 500:
                        captured_images[response.url] = body
            except Exception:
                pass

        page_hl.on("response", _on_response)

        try:
            page_hl.goto(url, wait_until="networkidle", timeout=30000)
        except Exception:
            page_hl.goto(url, wait_until="domcontentloaded", timeout=30000)
        page_hl.wait_for_timeout(2000)

        page_height = page_hl.evaluate("document.documentElement.scrollHeight")
        viewport_h = page_hl.evaluate("window.innerHeight")
        pos = 0
        while pos < page_height:
            page_hl.evaluate(f"window.scrollTo(0, {pos})")
            page_hl.wait_for_timeout(400)
            pos += viewport_h - 100
            page_height = page_hl.evaluate("document.documentElement.scrollHeight")

        page_hl.evaluate("window.scrollTo(0, 0)")
        page_hl.wait_for_timeout(500)

        print(f"Netzwerk-Interceptor: {len(captured_images)} Bilder abgefangen")

        images = page_hl.evaluate("""() => {
            const imgs = [];
            document.querySelectorAll('img').forEach(img => {
                const rect = img.getBoundingClientRect();
                imgs.push({
                    src: img.src || '',
                    currentSrc: img.currentSrc || '',
                    dataSrc: img.dataset.src || '',
                    naturalWidth: img.naturalWidth,
                    naturalHeight: img.naturalHeight,
                    x: Math.round(rect.x + window.scrollX),
                    y: Math.round(rect.y + window.scrollY),
                    displayWidth: Math.round(rect.width),
                    displayHeight: Math.round(rect.height)
                });
            });
            return imgs;
        }""")

        # Hash-Vergleich: Bilder aus Interceptor oder Fallback via Browser-Download
        best_match = None
        checked = 0
        debug_distances = []
        skipped = {"no_src": 0, "small_natural": 0, "download_fail": 0, "open_fail": 0, "small_img": 0}

        # Hilfsfunktion: Bild-Bytes holen (Interceptor → Browser-Fetch → requests.get)
        def _get_image_bytes(src):
            # 1. Aus Interceptor-Cache
            if src in captured_images:
                return captured_images[src]
            # Auch ohne Query-String oder mit anderem Schema versuchen
            for cached_url, data in captured_images.items():
                if cached_url.split("?")[0] == src.split("?")[0]:
                    return data
            # 2. Via Playwright evaluate (fetch im Browser-Kontext mit Cookies/Session)
            try:
                b64 = page_hl.evaluate("""(url) => {
                    return fetch(url, {credentials: 'include'})
                        .then(r => r.arrayBuffer())
                        .then(buf => {
                            const bytes = new Uint8Array(buf);
                            let binary = '';
                            for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
                            return btoa(binary);
                        })
                        .catch(() => null);
                }""", src)
                if b64:
                    return base64.b64decode(b64)
            except Exception:
                pass
            return None

        for i, img in enumerate(images):
            src = img["src"] or img["currentSrc"] or img["dataSrc"]
            if not src or src.startswith("data:"):
                skipped["no_src"] += 1
                continue
            if img["naturalWidth"] < 10 and img["displayWidth"] < 10:
                skipped["small_natural"] += 1
                print(f"  [{i}] SKIP: too small natural={img['naturalWidth']} display={img['displayWidth']}")
                continue
            try:
                img_bytes = _get_image_bytes(src)
                if not img_bytes or len(img_bytes) < 500:
                    skipped["download_fail"] += 1
                    print(f"  [{i}] SKIP: no data ({len(img_bytes) if img_bytes else 0} bytes) src={src[:80]}")
                    continue
                try:
                    web_img = Image.open(BytesIO(img_bytes))
                except Exception as img_err:
                    skipped["open_fail"] += 1
                    print(f"  [{i}] SKIP: PIL open failed: {img_err} src={src[:80]}")
                    continue
                if web_img.size[0] < 10:
                    skipped["small_img"] += 1
                    continue
                web_rgb = web_img.convert("RGB")
                dist = ref_hash - imagehash.phash(web_rgb, hash_size=16)
                checked += 1
                debug_distances.append({"src": src[:120], "distance": int(dist), "format": web_img.format})
                print(f"  [{i}] dist={dist} fmt={web_img.format} size={web_img.size} src={src[:100]}")
                if dist <= threshold and (best_match is None or dist < best_match["dist"]):
                    best_match = {"index": i, "dist": dist, "img": img, "src": src}
            except Exception as e:
                skipped["download_fail"] += 1
                print(f"  [{i}] FEHLER: {e} src={src[:100]}")
                continue

        browser_hl.close()

        print(f"Hash-Vergleich: {checked}/{len(images)} verglichen, skipped={skipped}, match={best_match is not None}")

        if not best_match:
            return {
                "success": False,
                "message": f"Kein Bild mit Distanz <= {threshold} gefunden",
                "images_checked": len(images),
                "images_compared": checked,
                "skipped": skipped,
                "distances": sorted(debug_distances, key=lambda d: d["distance"])[:10],
            }

        # ---- PHASE 2+3: Headed Browser → Desktop-Screenshot ----
        # Persistentes Profil für Login-Sessions verwenden
        CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

        # WICHTIG: Alte Chrome-Prozesse beenden und Lock-Dateien entfernen
        _kill_all_chrome_processes()
        _cleanup_chrome_locks()

        screen_w = os.environ.get('SCREEN_WIDTH', '1920')
        screen_h = os.environ.get('SCREEN_HEIGHT', '1080')

        ctx_opts = get_stealth_context_options()
        ctx_opts["no_viewport"] = True
        ctx_opts.pop("viewport", None)  # Entfernen da no_viewport=True

        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(CHROME_PROFILE_DIR),
            headless=False,
            args=[
                "--start-maximized",
                f"--window-size={screen_w},{screen_h}",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
            **ctx_opts,
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        apply_stealth_settings(page)

        # Fenster sofort maximieren bevor die Seite geladen wird
        time.sleep(1)
        _maximize_window(DISPLAY)
        time.sleep(0.5)

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        # Nochmals maximieren nach dem Laden
        _maximize_window(DISPLAY)
        time.sleep(0.5)

        page_height = page.evaluate("document.documentElement.scrollHeight")
        viewport_h = page.evaluate("window.innerHeight")
        pos = 0
        while pos < page_height:
            page.evaluate(f"window.scrollTo(0, {pos})")
            page.wait_for_timeout(400)
            pos += viewport_h - 100
            page_height = page.evaluate("document.documentElement.scrollHeight")

        img_y = best_match["img"]["y"]
        img_h = best_match["img"]["displayHeight"]
        scroll_to = max(0, img_y - (viewport_h - img_h) // 2)
        page.evaluate(f"window.scrollTo(0, {scroll_to})")
        page.wait_for_timeout(2000)

        screenshot_name = f"desktop_{job_id}.png"
        screenshot_path = OUTPUT_DIR / screenshot_name
        desktop_result = capture_xvfb_desktop(str(screenshot_path), DISPLAY)

        viewport_name = f"viewport_{job_id}.png"
        viewport_path = OUTPUT_DIR / viewport_name
        page.screenshot(path=str(viewport_path))

        ctx.close()  # Persistent context schließen (Cookies bleiben gespeichert)

    # Base64-Inline: Screenshots direkt in der Response mitgeben
    desktop_b64 = None
    viewport_b64 = None
    if desktop_result.success and screenshot_path.exists():
        desktop_b64 = base64.b64encode(screenshot_path.read_bytes()).decode("ascii")
    if viewport_path.exists():
        viewport_b64 = base64.b64encode(viewport_path.read_bytes()).decode("ascii")

    return {
        "success": True,
        "job_id": job_id,
        "match": {
            "url": best_match["src"],
            "distance": best_match["dist"],
            "position": {"x": best_match["img"]["x"], "y": best_match["img"]["y"]},
            "size": f"{best_match['img']['naturalWidth']}x{best_match['img']['naturalHeight']}",
        },
        "screenshots": {
            "desktop": f"/screenshots/{screenshot_name}" if desktop_result.success else None,
            "viewport": f"/screenshots/{viewport_name}",
        },
        "screenshots_base64": {
            "desktop": desktop_b64,
            "viewport": viewport_b64,
        },
        "images_checked": len(images),
    }


@app.post("/search", dependencies=[Depends(verify_api_key)])
async def search_image(
    request: Request,
    url: str = Form(..., description="Website-URL zum Durchsuchen"),
    reference: UploadFile = File(..., description="Referenzbild (JPG/PNG)"),
    threshold: int = Form(20, description="Max Hash-Distanz (0=identisch, <20=ähnlich)"),
):
    """
    3-Ebenen Bildsuche:
    1. Headless-Crawl → Bilder sammeln + Hash-Vergleich
    2. Playwright Viewport → zum Bild scrollen
    3. Xvfb Desktop-Screenshot → echte Browseransicht mit Adressleiste
    """
    _touch_activity()
    job_id = uuid.uuid4().hex[:8]
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"[{job_id}] POST /search | IP: {client_ip} | url={url} | threshold={threshold} | ref_file={reference.filename}")
    ref_data = await reference.read()

    result = await asyncio.to_thread(_run_search, url, ref_data, threshold, job_id)
    _touch_activity()

    if not result.get("success"):
        logger.warning(f"[{job_id}] /search FAILED | {result.get('message', 'unknown error')}")
        return JSONResponse(status_code=404, content=result)
    logger.info(f"[{job_id}] /search SUCCESS | match_distance={result.get('match', {}).get('distance')}")
    return result


def _kill_all_chrome_processes():
    """Beendet alle laufenden Chromium-Prozesse."""
    try:
        # Alle chrome/chromium Prozesse finden und beenden
        result = subprocess.run(
            ["pkill", "-f", "chrome"],
            capture_output=True,
            timeout=5
        )
        time.sleep(0.5)  # Kurz warten bis Prozesse beendet sind
    except Exception:
        pass


def _cleanup_chrome_locks():
    """Entfernt alle Chrome Lock-Dateien."""
    for lock_file in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
        lock_path = CHROME_PROFILE_DIR / lock_file
        try:
            if lock_path.exists():
                lock_path.unlink()
        except Exception:
            pass
    # Auch im Default-Profil aufräumen
    default_dir = CHROME_PROFILE_DIR / "Default"
    for lock_file in ["lockfile", "LOCK"]:
        lock_path = default_dir / lock_file
        try:
            if lock_path.exists():
                lock_path.unlink()
        except Exception:
            pass


def _run_screenshot(url: str, mode: str, scroll_to: int, full_page: bool, job_id: str, use_profile: bool = True) -> dict:
    """Reiner Screenshot ohne Bildvergleich – läuft in separatem Thread."""
    from playwright.sync_api import sync_playwright
    from src.screenshot.xvfb_screenshot import capture_xvfb_desktop

    # Thread-Lock: Nur ein Screenshot gleichzeitig
    with _screenshot_lock:
        screen_w = os.environ.get("SCREEN_WIDTH", "1920")
        screen_h = os.environ.get("SCREEN_HEIGHT", "1080")

        # Profil-Verzeichnis sicherstellen
        CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

        # Desktop-Modus mit Profil: Direkten Chrome-Start verwenden (wie Login-Session)
        # Damit werden die gespeicherten Cookies/Session korrekt übernommen
        if mode == "desktop" and use_profile:
            try:

                # WICHTIG: Alle alten Chrome-Prozesse beenden und Lock-Dateien entfernen
                _kill_all_chrome_processes()
                _cleanup_chrome_locks()

                # Chrome mit Profil starten
                env = {
                    **os.environ,
                    "DISPLAY": DISPLAY,
                    "GOOGLE_API_KEY": "no",
                    "GOOGLE_DEFAULT_CLIENT_ID": "no",
                    "GOOGLE_DEFAULT_CLIENT_SECRET": "no",
                }
                chromium_path = _get_chromium_path()

                cmd = [
                    chromium_path,
                    f"--user-data-dir={CHROME_PROFILE_DIR}",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--start-maximized",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-gpu",
                    "--disable-infobars",
                    "--disable-notifications",
                    url,
                ]
                print(f"Starting Chrome with cmd: {' '.join(cmd)}")
                proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                print(f"Chrome started with PID: {proc.pid}")

                # Warten und maximieren - Facebook braucht länger zum Laden (15 Sekunden wie manueller Test)
                time.sleep(12)

                # Prüfen ob Chrome noch läuft
                poll_result = proc.poll()
                print(f"Chrome poll after 12s: {poll_result} (None = still running)")
                if poll_result is not None:
                    stderr_output = proc.stderr.read().decode() if proc.stderr else "no stderr"
                    print(f"Chrome stderr: {stderr_output[:1000]}")

                _maximize_window(DISPLAY)
                time.sleep(3)

                # Double-Screenshot: Erster Screenshot triggert Lazy-Loading der Bilder
                screenshot_name = f"desktop_{job_id}.png"
                screenshot_path = OUTPUT_DIR / screenshot_name
                capture_xvfb_desktop(str(screenshot_path), DISPLAY)
                print("First screenshot taken, waiting for images to load...")

                # Warten bis Bilder nachgeladen sind (10 Sekunden für langsame Facebook-Bilder)
                time.sleep(10)

                # Zweiter Screenshot - jetzt sollten alle Bilder geladen sein
                result = capture_xvfb_desktop(str(screenshot_path), DISPLAY)
                print("Second screenshot taken")

                # Browser schließen
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

                if result.success:
                    with open(screenshot_path, "rb") as f:
                        screenshot_b64 = base64.b64encode(f.read()).decode()
                    return {
                        "success": True,
                        "job_id": job_id,
                        "mode": mode,
                        "full_page": full_page,
                        "screenshot": f"/screenshots/{screenshot_name}",
                        "screenshot_base64": screenshot_b64,
                    }
                else:
                    return {"success": False, "error": result.error}

            except Exception as e:
                # Bei Fehler auch Chrome beenden
                _kill_all_chrome_processes()
                return {"success": False, "error": str(e)}

        # Viewport-Modus oder ohne Profil: Playwright verwenden
        with sync_playwright() as p:
            headless = (mode == "viewport")
            args = [
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ]
            if not headless:
                args += ["--start-maximized", f"--window-size={screen_w},{screen_h}", "--disable-gpu"]

            # Desktop-Modus ohne Profil: Playwright persistent context
            if not headless and use_profile:
                ctx_opts = get_stealth_context_options()
                ctx_opts["no_viewport"] = True
                ctx_opts.pop("viewport", None)
                ctx = p.chromium.launch_persistent_context(
                    user_data_dir=str(CHROME_PROFILE_DIR),
                    headless=False,
                    args=args,
                    **ctx_opts,
                )
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                browser = None
            else:
                browser = p.chromium.launch(headless=headless, args=args)
                ctx_opts = get_stealth_context_options()
                if not headless:
                    ctx_opts["no_viewport"] = True
                    ctx_opts.pop("viewport", None)
                ctx = browser.new_context(**ctx_opts)
                page = ctx.new_page()

            apply_stealth_settings(page)

            if not headless:
                time.sleep(1)
                _maximize_window(DISPLAY)
                time.sleep(0.5)

            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
            except Exception:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            if not headless:
                _maximize_window(DISPLAY)
                time.sleep(0.5)

            # Lazy-Load auslösen: einmal komplett durchscrollen
            page_height = page.evaluate("document.documentElement.scrollHeight")
            viewport_h = page.evaluate("window.innerHeight")
            pos = 0
            while pos < page_height:
                page.evaluate(f"window.scrollTo(0, {pos})")
                page.wait_for_timeout(400)
                pos += viewport_h - 100
                page_height = page.evaluate("document.documentElement.scrollHeight")

            # Zur gewünschten Position scrollen
            if scroll_to > 0:
                page.evaluate(f"window.scrollTo(0, {scroll_to})")
            else:
                page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(1500)

            if mode == "desktop":
                filename = f"desktop_{job_id}.png"
                filepath = OUTPUT_DIR / filename
                desktop_result = capture_xvfb_desktop(str(filepath), DISPLAY)
                if not desktop_result.success:
                    ctx.close()
                    return {"success": False, "message": "Desktop-Screenshot fehlgeschlagen"}
            else:
                filename = f"viewport_{job_id}.png"
                filepath = OUTPUT_DIR / filename
                page.screenshot(path=str(filepath), full_page=full_page)

            ctx.close()

        # Base64-Inline: Screenshot direkt in der Response
        screenshot_b64 = None
        if filepath.exists():
            screenshot_b64 = base64.b64encode(filepath.read_bytes()).decode("ascii")

        return {
            "success": True,
            "job_id": job_id,
            "mode": mode,
            "full_page": full_page,
            "screenshot": f"/screenshots/{filename}",
            "screenshot_base64": screenshot_b64,
        }


@app.post("/screenshot", dependencies=[Depends(verify_api_key)])
async def take_screenshot(
    request: Request,
    url: str = Form(..., description="Website-URL"),
    mode: str = Form("desktop", description="Screenshot-Modus: 'desktop' oder 'viewport'"),
    scroll_to: int = Form(0, description="Scroll-Position in Pixeln (0 = Seitenanfang)"),
    full_page: bool = Form(False, description="Gesamte Seite erfassen (nur bei mode=viewport)"),
    use_profile: bool = Form(True, description="Persistentes Browser-Profil nutzen (für Login-Sessions)"),
):
    """
    Reiner Screenshot ohne Bildvergleich.
    - desktop:  Xvfb-Framebuffer (echte Browseransicht mit Adressleiste)
    - viewport: Playwright-Viewport (nur Seiteninhalt, ohne Browser-Chrome)
    - full_page: Bei viewport=true wird die gesamte Seite erfasst (scroll_to wird ignoriert)
    - use_profile: Bei True wird das persistente Browser-Profil verwendet (Login-Sessions)
    """
    _touch_activity()
    job_id = uuid.uuid4().hex[:8]
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"[{job_id}] POST /screenshot | IP: {client_ip} | url={url} | mode={mode} | scroll={scroll_to} | full_page={full_page} | profile={use_profile}")

    if mode not in ("desktop", "viewport"):
        logger.warning(f"[{job_id}] /screenshot INVALID MODE: {mode}")
        raise HTTPException(status_code=400, detail="mode muss 'desktop' oder 'viewport' sein")

    result = await asyncio.to_thread(_run_screenshot, url, mode, scroll_to, full_page, job_id, use_profile)
    _touch_activity()

    if not result.get("success"):
        logger.warning(f"[{job_id}] /screenshot FAILED | {result.get('error', result.get('message', 'unknown'))}")
        return JSONResponse(status_code=500, content=result)
    logger.info(f"[{job_id}] /screenshot SUCCESS | file={result.get('screenshot')}")
    return result


@app.get("/screenshots/{filename}", dependencies=[Depends(verify_api_key)])
async def get_screenshot(filename: str):
    """Screenshot-Datei abrufen."""
    # Nur Dateinamen zulassen (kein Path-Traversal)
    safe_name = Path(filename).name
    filepath = OUTPUT_DIR / safe_name
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Screenshot nicht gefunden")
    return FileResponse(filepath, media_type="image/png")


# ============================================================
# LOGIN-SESSION MANAGEMENT
# ============================================================

def _get_chromium_path() -> str:
    """Findet den Playwright-Chromium-Pfad."""
    import glob
    patterns = [
        "/root/.cache/ms-playwright/chromium-*/chrome-linux/chrome",
        "/home/*/.cache/ms-playwright/chromium-*/chrome-linux/chrome",
    ]
    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
    # Fallback
    return "/root/.cache/ms-playwright/chromium-1105/chrome-linux/chrome"


def _start_chromium_with_profile(url: str = "https://www.facebook.com") -> subprocess.Popen:
    """Startet Chromium mit persistentem Profil auf dem Xvfb-Desktop."""
    env = {
        **os.environ,
        "DISPLAY": DISPLAY,
        "GOOGLE_API_KEY": "no",
        "GOOGLE_DEFAULT_CLIENT_ID": "no",
        "GOOGLE_DEFAULT_CLIENT_SECRET": "no",
    }
    chromium_path = _get_chromium_path()
    cmd = [
        chromium_path,
        f"--user-data-dir={CHROME_PROFILE_DIR}",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--start-maximized",
        "--disable-blink-features=AutomationControlled",
        "--disable-gpu",
        "--disable-infobars",
        "--disable-notifications",
        url,
    ]
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc


@app.post("/login-session/start", dependencies=[Depends(verify_api_key)])
async def start_login_session(
    request: Request,
    url: str = Form("https://www.facebook.com/login", description="Login-URL (default: Facebook)"),
):
    """
    Startet eine Login-Session mit persistentem Browser-Profil.

    1. Öffnet Chromium auf dem Xvfb-Desktop
    2. Verbinde dich via noVNC (Port 6080) und logge dich manuell ein
    3. Beende mit /login-session/stop wenn fertig

    Die Session (Cookies, Login) wird dauerhaft im Profil gespeichert.
    """
    _touch_activity()
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"POST /login-session/start | IP: {client_ip} | url={url}")
    global _active_login_session

    # Alte Session beenden falls vorhanden
    if _active_login_session and _active_login_session.poll() is None:
        _active_login_session.terminate()
        _active_login_session.wait(timeout=5)

    _active_login_session = _start_chromium_with_profile(url)

    # Kurz warten und Fenster maximieren
    await asyncio.sleep(2)
    _maximize_window(DISPLAY)

    return {
        "success": True,
        "message": "Login-Session gestartet",
        "instructions": [
            "1. Öffne noVNC im Browser: http://<host>:6080",
            "2. Logge dich manuell bei der Website ein",
            "3. Rufe /login-session/stop auf wenn fertig",
        ],
        "url": url,
        "novnc_hint": "Verbinde dich via Port 6080 (noVNC)",
    }


@app.post("/login-session/stop", dependencies=[Depends(verify_api_key)])
async def stop_login_session(request: Request):
    """
    Beendet die aktive Login-Session.

    Die Cookies/Session bleiben im persistenten Profil gespeichert
    und werden bei zukünftigen Screenshots automatisch verwendet.
    """
    _touch_activity()
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"POST /login-session/stop | IP: {client_ip}")
    global _active_login_session

    if _active_login_session is None:
        return {"success": False, "message": "Keine aktive Login-Session"}

    if _active_login_session.poll() is None:
        _active_login_session.terminate()
        try:
            _active_login_session.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _active_login_session.kill()

    _active_login_session = None

    return {
        "success": True,
        "message": "Login-Session beendet. Cookies wurden gespeichert.",
    }


@app.get("/login-session/status", dependencies=[Depends(verify_api_key)])
async def login_session_status():
    """
    Prüft den Status der Login-Session und vorhandene Cookies.
    """
    _touch_activity()
    global _active_login_session

    session_active = _active_login_session is not None and _active_login_session.poll() is None

    # Prüfe ob Profil existiert und Cookies enthält
    cookies_file = CHROME_PROFILE_DIR / "Default" / "Cookies"
    profile_exists = CHROME_PROFILE_DIR.exists()
    cookies_exist = cookies_file.exists()

    # Bekannte Login-Domains prüfen (vereinfacht)
    known_logins = []
    if cookies_exist:
        # Grobe Prüfung: Datei > 10KB deutet auf gespeicherte Cookies hin
        if cookies_file.stat().st_size > 10000:
            known_logins.append("cookies_present")

    return {
        "session_active": session_active,
        "profile_exists": profile_exists,
        "cookies_exist": cookies_exist,
        "cookies_file_size": cookies_file.stat().st_size if cookies_exist else 0,
        "known_logins": known_logins,
        "profile_path": str(CHROME_PROFILE_DIR),
    }


@app.delete("/login-session/clear", dependencies=[Depends(verify_api_key)])
async def clear_login_session():
    """
    Löscht das gesamte Browser-Profil (alle Cookies, Logins, etc.).
    """
    _touch_activity()
    global _active_login_session

    # Session beenden falls aktiv
    if _active_login_session and _active_login_session.poll() is None:
        _active_login_session.terminate()
        _active_login_session.wait(timeout=5)
        _active_login_session = None

    import shutil
    if CHROME_PROFILE_DIR.exists():
        shutil.rmtree(CHROME_PROFILE_DIR)
        CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        return {"success": True, "message": "Browser-Profil gelöscht"}

    return {"success": True, "message": "Kein Profil vorhanden"}

