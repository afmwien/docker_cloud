"""
Window Manager - Fenster-Positionierung und -Maximierung für Playwright

Verwendet Windows API (ctypes) für zuverlässige Fenstersteuerung.
"""

import ctypes
import time
from typing import Tuple, Optional
from dataclasses import dataclass
from playwright.sync_api import Page

# Windows API Konstanten
SW_MAXIMIZE = 3
SW_RESTORE = 9
SW_SHOWMAXIMIZED = 3
HWND_TOP = 0
SWP_SHOWWINDOW = 0x0040


@dataclass
class WindowConfig:
    """Fenster-Konfiguration."""
    maximize: bool = True
    width: int = 1920
    height: int = 1080
    x: int = 0
    y: int = 0


class WindowManager:
    """
    Verwaltet die Fensterposition und -größe.

    Verwendet Windows API für zuverlässige Maximierung.

    Verwendung:
        wm = WindowManager(page)
        wm.maximize()
        # oder
        wm.set_size(1920, 1080)
    """

    def __init__(self, page: Page):
        self.page = page
        self._user32 = ctypes.windll.user32

    def maximize(self) -> bool:
        """Maximiert das Browser-Fenster via Windows API."""
        try:
            # Fenster in Vordergrund bringen
            self.page.bring_to_front()
            time.sleep(0.2)

            # Aktuelles Vordergrund-Fenster finden
            hwnd = self._get_foreground_window()

            if hwnd:
                # Fenster maximieren via ShowWindow
                self._user32.ShowWindow(hwnd, SW_MAXIMIZE)
                time.sleep(0.3)
                return True

            # Fallback: Chromium-Fenster suchen
            hwnd = self._find_chrome_window()
            if hwnd:
                self._user32.ShowWindow(hwnd, SW_MAXIMIZE)
                self._user32.SetForegroundWindow(hwnd)
                time.sleep(0.3)
                return True

            return False
        except Exception as e:
            print(f"Maximize error: {e}")
            return False

    def _get_foreground_window(self) -> Optional[int]:
        """Gibt das aktuelle Vordergrund-Fenster zurück."""
        try:
            return self._user32.GetForegroundWindow()
        except:
            return None

    def _find_chrome_window(self) -> Optional[int]:
        """Findet das Chrome/Chromium-Fenster."""
        try:
            # Nach Chromium-Fenstern suchen
            EnumWindows = ctypes.windll.user32.EnumWindows
            EnumWindowsProc = ctypes.WINFUNCTYPE(
                ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
            )
            GetWindowText = ctypes.windll.user32.GetWindowTextW
            GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
            IsWindowVisible = ctypes.windll.user32.IsWindowVisible

            found_hwnd = None

            def enum_callback(hwnd, lParam):
                nonlocal found_hwnd
                if IsWindowVisible(hwnd):
                    length = GetWindowTextLength(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        GetWindowText(hwnd, buff, length + 1)
                        title = buff.value.lower()
                        # Chrome-artige Titel suchen
                        if 'chrome' in title or 'chromium' in title:
                            found_hwnd = hwnd
                            return False  # Stop enumeration
                return True  # Continue enumeration

            EnumWindows(EnumWindowsProc(enum_callback), 0)
            return found_hwnd
        except:
            return None

    def set_window_rect(self, x: int, y: int, width: int, height: int) -> bool:
        """Setzt Position und Größe des Fensters."""
        try:
            hwnd = self._get_foreground_window()
            if hwnd:
                # Erst aus Maximierung holen
                self._user32.ShowWindow(hwnd, SW_RESTORE)
                time.sleep(0.1)
                # Dann Position/Größe setzen
                self._user32.MoveWindow(hwnd, x, y, width, height, True)
                return True
            return False
        except:
            return False

    def bring_to_front(self) -> bool:
        """Bringt das Fenster in den Vordergrund."""
        try:
            self.page.bring_to_front()
            hwnd = self._get_foreground_window()
            if hwnd:
                self._user32.SetForegroundWindow(hwnd)
            return True
        except:
            return False

    def _get_screen_size(self) -> Tuple[int, int]:
        """Ermittelt die Bildschirmgröße."""
        try:
            width = self._user32.GetSystemMetrics(0)
            height = self._user32.GetSystemMetrics(1)
            return width, height
        except:
            return 1920, 1080

    def get_viewport_size(self) -> Tuple[int, int]:
        """Gibt die aktuelle Viewport-Größe zurück."""
        try:
            size = self.page.evaluate("""
                () => ({
                    width: window.innerWidth,
                    height: window.innerHeight
                })
            """)
            return size["width"], size["height"]
        except:
            return 0, 0

    def fullscreen(self) -> bool:
        """Wechselt in den Vollbildmodus (F11)."""
        try:
            self.page.keyboard.press("F11")
            return True
        except:
            return False

    def exit_fullscreen(self) -> bool:
        """Beendet den Vollbildmodus."""
        return self.fullscreen()  # F11 toggled
