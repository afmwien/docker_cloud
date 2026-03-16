"""
Cookie Handler Module - Robustes Cookie-Consent-Management für Playwright
"""
from .cookie_handler import (
    CookieHandler,
    CookieHandlerConfig,
    CookieHandlerResult,
    ConsentAction,
    CMPType,
    create_cookie_aware_context,
)
from .consent_patterns import ConsentPatterns, KNOWN_COOKIE_VALUES

__all__ = [
    "CookieHandler",
    "CookieHandlerConfig",
    "CookieHandlerResult",
    "ConsentAction",
    "CMPType",
    "ConsentPatterns",
    "KNOWN_COOKIE_VALUES",
    "create_cookie_aware_context",
]
