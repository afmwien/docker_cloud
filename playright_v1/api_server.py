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
from pathlib import Path
from io import BytesIO

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Security, Depends
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from PIL import Image
import imagehash
import requests as req

sys.path.insert(0, str(Path(__file__).parent / "src"))

from browser.stealth import apply_stealth_settings, get_stealth_context_options
from screenshot.xvfb_screenshot import capture_xvfb_desktop

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
        screen_w = os.environ.get('SCREEN_WIDTH', '1920')
        screen_h = os.environ.get('SCREEN_HEIGHT', '1080')
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--start-maximized",
                f"--window-size={screen_w},{screen_h}",
                "--disable-gpu",
                "--no-sandbox",
            ]
        )
        ctx = browser.new_context(
            **get_stealth_context_options(),
            no_viewport=True,
        )
        page = ctx.new_page()
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

        browser.close()

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
    ref_data = await reference.read()

    result = await asyncio.to_thread(_run_search, url, ref_data, threshold, job_id)
    _touch_activity()

    if not result.get("success"):
        return JSONResponse(status_code=404, content=result)
    return result


def _run_screenshot(url: str, mode: str, scroll_to: int, full_page: bool, job_id: str) -> dict:
    """Reiner Screenshot ohne Bildvergleich – läuft in separatem Thread."""
    from playwright.sync_api import sync_playwright

    screen_w = os.environ.get("SCREEN_WIDTH", "1920")
    screen_h = os.environ.get("SCREEN_HEIGHT", "1080")

    with sync_playwright() as p:
        headless = (mode == "viewport")
        args = ["--no-sandbox"]
        if not headless:
            args += ["--start-maximized", f"--window-size={screen_w},{screen_h}", "--disable-gpu"]

        browser = p.chromium.launch(headless=headless, args=args)

        ctx_opts = get_stealth_context_options()
        if not headless:
            ctx_opts["no_viewport"] = True
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
                browser.close()
                return {"success": False, "message": "Desktop-Screenshot fehlgeschlagen"}
        else:
            filename = f"viewport_{job_id}.png"
            filepath = OUTPUT_DIR / filename
            page.screenshot(path=str(filepath), full_page=full_page)

        browser.close()

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
    url: str = Form(..., description="Website-URL"),
    mode: str = Form("desktop", description="Screenshot-Modus: 'desktop' oder 'viewport'"),
    scroll_to: int = Form(0, description="Scroll-Position in Pixeln (0 = Seitenanfang)"),
    full_page: bool = Form(False, description="Gesamte Seite erfassen (nur bei mode=viewport)"),
):
    """
    Reiner Screenshot ohne Bildvergleich.
    - desktop:  Xvfb-Framebuffer (echte Browseransicht mit Adressleiste)
    - viewport: Playwright-Viewport (nur Seiteninhalt, ohne Browser-Chrome)
    - full_page: Bei viewport=true wird die gesamte Seite erfasst (scroll_to wird ignoriert)
    """
    _touch_activity()

    if mode not in ("desktop", "viewport"):
        raise HTTPException(status_code=400, detail="mode muss 'desktop' oder 'viewport' sein")

    job_id = uuid.uuid4().hex[:8]
    result = await asyncio.to_thread(_run_screenshot, url, mode, scroll_to, full_page, job_id)
    _touch_activity()

    if not result.get("success"):
        return JSONResponse(status_code=500, content=result)
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
