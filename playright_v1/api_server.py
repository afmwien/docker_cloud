"""
FastAPI Server für die 3-Ebenen Bildsuche mit Desktop-Screenshot.

Endpunkte:
  POST /search          - Bildsuche starten (URL + Referenzbild)
  GET  /health          - Health-Check
  GET  /screenshots/{f} - Screenshots abrufen
"""

import sys
import os
import uuid
import time
import subprocess
from pathlib import Path
from io import BytesIO

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image
import imagehash

sys.path.insert(0, str(Path(__file__).parent / "src"))

from browser.stealth import apply_stealth_settings, get_stealth_context_options
from screenshot.xvfb_screenshot import capture_xvfb_desktop

app = FastAPI(title="Image Finder Desktop", version="1.0.0")

DISPLAY = os.environ.get("DISPLAY", ":99")
OUTPUT_DIR = Path("/app/output/screenshots")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/health")
async def health():
    return {"status": "healthy", "display": DISPLAY}


@app.post("/search")
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
    job_id = uuid.uuid4().hex[:8]

    # Referenzbild laden und hashen
    ref_data = await reference.read()
    ref_img = Image.open(BytesIO(ref_data))
    ref_hash = imagehash.phash(ref_img, hash_size=16)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        # ---- PHASE 1: Headless Crawl (Bilder finden) ----
        browser_hl = p.chromium.launch(headless=True)
        ctx_hl = browser_hl.new_context(**get_stealth_context_options())
        page_hl = ctx_hl.new_page()
        apply_stealth_settings(page_hl)

        try:
            page_hl.goto(url, wait_until="networkidle", timeout=30000)
        except Exception:
            page_hl.goto(url, wait_until="domcontentloaded", timeout=30000)
        page_hl.wait_for_timeout(2000)

        # Scrollen für Lazy-Loading
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

        # Bilder sammeln
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

        browser_hl.close()

        # Hash-Vergleich
        import requests as req
        best_match = None

        for i, img in enumerate(images):
            src = img["currentSrc"] or img["src"] or img["dataSrc"]
            if not src or img["naturalWidth"] < 10:
                continue
            try:
                resp = req.get(src, timeout=5, verify=False)
                if resp.status_code == 200 and len(resp.content) > 500:
                    web_img = Image.open(BytesIO(resp.content))
                    if web_img.size[0] > 10:
                        dist = ref_hash - imagehash.phash(web_img, hash_size=16)
                        if dist <= threshold and (best_match is None or dist < best_match["dist"]):
                            best_match = {"index": i, "dist": dist, "img": img, "src": src}
            except Exception:
                continue

        if not best_match:
            return JSONResponse(status_code=404, content={
                "success": False,
                "message": f"Kein Bild mit Distanz <= {threshold} gefunden",
                "images_checked": len(images),
            })

        # ---- PHASE 2+3: Headed Browser auf Xvfb → Desktop-Screenshot ----
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--start-maximized",
                f"--window-size={os.environ.get('SCREEN_WIDTH', '1920')},{os.environ.get('SCREEN_HEIGHT', '1080')}",
                "--disable-gpu",
                "--no-sandbox",
            ]
        )
        ctx = browser.new_context(
            **get_stealth_context_options(),
            no_viewport=True,  # Nutzt die tatsächliche Fenstergröße
        )
        page = ctx.new_page()
        apply_stealth_settings(page)

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # Scrollen für Lazy-Loading
        page_height = page.evaluate("document.documentElement.scrollHeight")
        viewport_h = page.evaluate("window.innerHeight")
        pos = 0
        while pos < page_height:
            page.evaluate(f"window.scrollTo(0, {pos})")
            page.wait_for_timeout(400)
            pos += viewport_h - 100
            page_height = page.evaluate("document.documentElement.scrollHeight")

        # Zum gefundenen Bild scrollen (zentriert im Viewport)
        img_y = best_match["img"]["y"]
        img_h = best_match["img"]["displayHeight"]
        scroll_to = max(0, img_y - (viewport_h - img_h) // 2)
        page.evaluate(f"window.scrollTo(0, {scroll_to})")
        page.wait_for_timeout(2000)

        # Fenster maximieren via xdotool
        try:
            subprocess.run(
                ["xdotool", "key", "super+Up"],
                env={**os.environ, "DISPLAY": DISPLAY},
                timeout=5,
            )
            time.sleep(0.5)
        except Exception:
            pass

        # ---- Desktop-Screenshot (Xvfb Framebuffer) ----
        screenshot_name = f"desktop_{job_id}.png"
        screenshot_path = OUTPUT_DIR / screenshot_name

        desktop_result = capture_xvfb_desktop(
            output_path=str(screenshot_path),
            display=DISPLAY
        )

        # Auch einen Playwright-Viewport-Screenshot (Ebene 2)
        viewport_name = f"viewport_{job_id}.png"
        viewport_path = OUTPUT_DIR / viewport_name
        page.screenshot(path=str(viewport_path))

        browser.close()

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
        "images_checked": len(images),
    }


@app.get("/screenshots/{filename}")
async def get_screenshot(filename: str):
    """Screenshot-Datei abrufen."""
    # Nur Dateinamen zulassen (kein Path-Traversal)
    safe_name = Path(filename).name
    filepath = OUTPUT_DIR / safe_name
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Screenshot nicht gefunden")
    return FileResponse(filepath, media_type="image/png")
