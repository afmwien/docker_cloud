"""
X11/Xvfb Desktop-Screenshot

Erfasst den gesamten virtuellen Desktop (Xvfb Framebuffer)
inkl. Fensterrahmen, Adressleiste, Taskbar – wie ein echter Monitor.
"""

import subprocess
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class DesktopScreenshotResult:
    success: bool
    filepath: Optional[Path] = None
    width: int = 0
    height: int = 0
    error: Optional[str] = None


def capture_xvfb_desktop(
    output_path: str,
    display: str = ":99"
) -> DesktopScreenshotResult:
    """
    Erfasst den gesamten Xvfb-Desktop als PNG.

    Verwendet ImageMagick 'import' für den Screenshot des root-Windows,
    was den kompletten Framebuffer inkl. aller Fensterdekorationen erfasst.
    """
    env = os.environ.copy()
    env["DISPLAY"] = display

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        # ImageMagick: Screenshot des gesamten Root-Windows
        result = subprocess.run(
            ["import", "-window", "root", str(output)],
            env=env,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            # Fallback: scrot
            result = subprocess.run(
                ["scrot", str(output)],
                env=env,
                capture_output=True,
                text=True,
                timeout=10
            )

        if result.returncode == 0 and output.exists():
            from PIL import Image
            img = Image.open(output)
            return DesktopScreenshotResult(
                success=True,
                filepath=output,
                width=img.size[0],
                height=img.size[1]
            )

        return DesktopScreenshotResult(
            success=False,
            error=f"Screenshot fehlgeschlagen: {result.stderr}"
        )

    except Exception as e:
        return DesktopScreenshotResult(
            success=False,
            error=str(e)
        )
