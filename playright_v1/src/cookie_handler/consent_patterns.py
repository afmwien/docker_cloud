"""
Consent Patterns - Umfangreiche Sammlung von Cookie-Banner-Selektoren

Unterstützte Consent Management Platforms (CMPs):
- OneTrust
- CookieBot
- Borlabs Cookie
- Complianz
- GDPR Cookie Consent
- Cookie Notice
- CookieYes
- Klaro
- Osano
- TrustArc
- Usercentrics
- Didomi
- Quantcast
- Iubenda
- Cookie Script
- Generische Patterns
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class ConsentPatterns:
    """
    Sammlung aller Cookie-Consent-Selektoren nach Kategorien.
    """

    # =========================================================================
    # ACCEPT-BUTTON SELEKTOREN
    # =========================================================================

    # Mehrsprachige Text-basierte Selektoren
    accept_text_patterns: List[str] = field(default_factory=lambda: [
        # Deutsch
        "text=Alle akzeptieren",
        "text=Akzeptieren",
        "text=Alle Cookies akzeptieren",
        "text=Cookies akzeptieren",
        "text=Zustimmen",
        "text=Alle zulassen",
        "text=Einverstanden",
        "text=OK",
        "text=Verstanden",
        "text=Ich stimme zu",
        "text=Alles akzeptieren",
        "text=Annehmen",

        # Englisch
        "text=Accept All",
        "text=Accept all cookies",
        "text=Accept",
        "text=Allow All",
        "text=Allow all",
        "text=I Accept",
        "text=I Agree",
        "text=Agree",
        "text=Got it",
        "text=OK",
        "text=Consent",
        "text=Allow Cookies",

        # Französisch
        "text=Accepter tout",
        "text=Tout accepter",
        "text=J'accepte",
        "text=Accepter",

        # Spanisch
        "text=Aceptar todo",
        "text=Aceptar todas",
        "text=Aceptar",

        # Italienisch
        "text=Accetta tutto",
        "text=Accetta",

        # Niederländisch
        "text=Alles accepteren",
        "text=Accepteren",

        # Polnisch
        "text=Zaakceptuj wszystkie",
        "text=Akceptuję",
    ])

    # OneTrust Selektoren
    onetrust_selectors: List[str] = field(default_factory=lambda: [
        "#onetrust-accept-btn-handler",
        "#accept-recommended-btn-handler",
        ".onetrust-accept-btn-handler",
        "[data-testid='onetrust-accept-btn-handler']",
        "#onetrust-banner-sdk button.onetrust-accept-btn-handler",
        ".ot-sdk-container #onetrust-accept-btn-handler",
    ])

    # CookieBot Selektoren
    cookiebot_selectors: List[str] = field(default_factory=lambda: [
        "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
        "#CybotCookiebotDialogBodyButtonAccept",
        "#CybotCookiebotDialogBodyLevelButtonAccept",
        "[data-cookieconsent='accept']",
        ".CybotCookiebotDialogBodyButton[id*='Accept']",
        "#Cookiebot .CybotCookiebotDialogBodyButton",
    ])

    # Borlabs Cookie Selektoren
    borlabs_selectors: List[str] = field(default_factory=lambda: [
        ".BorlabsCookie button[data-cookie-accept-all]",
        "[data-cookie-accept-all]",
        ".borlabs-cookie-accept-all",
        "#BorlabsCookieBoxWrap a._brlbs-btn-accept-all",
        ".BorlabsCookie ._brlbs-accept-all",
        "#BorlabsCookieBox a[data-cookie-accept-all='true']",
    ])

    # Complianz Selektoren
    complianz_selectors: List[str] = field(default_factory=lambda: [
        ".cmplz-accept",
        ".cmplz-btn.cmplz-accept",
        "#cmplz-cookiebanner-container .cmplz-accept",
        "[data-cmplz-accept='all']",
        ".cmplz-accept-all",
    ])

    # Cookie Notice / Cookie Law Info Selektoren
    cookie_notice_selectors: List[str] = field(default_factory=lambda: [
        "#cookie-notice-accept-all",
        "#cn-accept-cookie",
        ".cn-accept-cookie",
        "#cookie-law-info-bar .cli-plugin-button",
        ".cli_action_button[data-cli_action='accept_all']",
        "#cookie_action_close_header",
        "#wt-cli-accept-all-btn",
    ])

    # CookieYes Selektoren
    cookieyes_selectors: List[str] = field(default_factory=lambda: [
        ".cky-btn-accept",
        "[data-cky-tag='accept-button']",
        ".cky-consent-bar .cky-btn-accept",
        "#ckyBtnAcceptAll",
    ])

    # Klaro Selektoren
    klaro_selectors: List[str] = field(default_factory=lambda: [
        ".klaro .cm-btn-accept-all",
        ".klaro .cm-btn-accept",
        ".klaro button.cm-btn-success",
        "[data-klaro-action='accept']",
    ])

    # Osano Selektoren
    osano_selectors: List[str] = field(default_factory=lambda: [
        ".osano-cm-accept-all",
        ".osano-cm-button--type_accept",
        "[data-osano='accept']",
    ])

    # TrustArc Selektoren
    trustarc_selectors: List[str] = field(default_factory=lambda: [
        ".trustarc-agree-btn",
        "#truste-consent-button",
        ".truste_overlay .truste-button2",
        "[data-trustarc='accept']",
    ])

    # Usercentrics Selektoren
    usercentrics_selectors: List[str] = field(default_factory=lambda: [
        "#uc-btn-accept-banner",
        "[data-testid='uc-accept-all-button']",
        ".uc-btn-accept",
        "#usercentrics-button",
    ])

    # Didomi Selektoren
    didomi_selectors: List[str] = field(default_factory=lambda: [
        "#didomi-notice-agree-button",
        ".didomi-continue-without-agreeing",
        "[data-testid='didomi-notice-agree-button']",
        ".didomi-button-highlight",
    ])

    # Quantcast Selektoren
    quantcast_selectors: List[str] = field(default_factory=lambda: [
        ".qc-cmp2-summary-buttons button[mode='primary']",
        ".qc-cmp-button",
        "#qc-cmp2-ui button.css-47sehv",
        "[data-tracking-opt-in-accept]",
    ])

    # Iubenda Selektoren
    iubenda_selectors: List[str] = field(default_factory=lambda: [
        ".iubenda-cs-accept-btn",
        "#iubenda-cs-banner .iubenda-cs-accept-btn",
        "[data-iub-action='accept']",
    ])

    # Cookie Script Selektoren
    cookiescript_selectors: List[str] = field(default_factory=lambda: [
        "#cookiescript_accept",
        ".cookiescript_accept",
        "[data-cs-accept-all]",
    ])

    # Generische Selektoren (CSS-basiert)
    generic_css_selectors: List[str] = field(default_factory=lambda: [
        # ID-basiert
        "[id*='cookie'][id*='accept']",
        "[id*='consent'][id*='accept']",
        "[id*='gdpr'][id*='accept']",
        "[id*='privacy'][id*='accept']",
        "#accept-cookies",
        "#acceptCookies",
        "#cookie-accept",
        "#cookieAccept",
        "#consent-accept",
        "#gdpr-accept",

        # Class-basiert
        "[class*='cookie'][class*='accept']",
        "[class*='consent'][class*='accept']",
        "[class*='gdpr'][class*='accept']",
        ".cookie-accept",
        ".accept-cookie",
        ".consent-accept",
        ".gdpr-accept",
        ".cc-accept",
        ".cc-allow",
        ".cc-dismiss",

        # Data-Attribute
        "[data-action='accept']",
        "[data-consent='accept']",
        "[data-cookie-accept]",
        "[data-gdpr-accept]",
        "button[data-accept]",
        "[data-testid*='accept']",
        "[data-cy*='accept']",

        # Aria-Label
        "[aria-label*='accept' i]",
        "[aria-label*='akzeptieren' i]",
        "[aria-label*='zustimmen' i]",

        # Button innerhalb Cookie-Container
        "[class*='cookie'] button:not([class*='reject']):not([class*='decline'])",
        "[class*='consent'] button:not([class*='reject']):not([class*='decline'])",
        "[id*='cookie'] button:not([id*='reject']):not([id*='decline'])",
        "[id*='consent'] button:not([id*='reject']):not([id*='decline'])",

        # Modal/Banner Buttons
        ".modal[class*='cookie'] .btn-primary",
        ".banner[class*='cookie'] button",
        "[role='dialog'][class*='cookie'] button",
        "[role='alertdialog'] button[class*='accept']",
    ])

    # =========================================================================
    # BANNER DETECTION SELEKTOREN
    # =========================================================================

    banner_detection_selectors: List[str] = field(default_factory=lambda: [
        # CMP-spezifisch
        "#onetrust-banner-sdk",
        "#CybotCookiebotDialog",
        "#BorlabsCookieBox",
        "#cmplz-cookiebanner-container",
        "#cookie-notice",
        "#cookie-law-info-bar",
        ".cky-consent-container",
        ".klaro",
        ".osano-cm-dialog",
        "#truste-consent-track",
        "#usercentrics-root",
        "#didomi-host",
        ".qc-cmp2-container",
        "#iubenda-cs-banner",
        "#cookiescript_injected",

        # Generisch
        "[class*='cookie-banner']",
        "[class*='cookie-notice']",
        "[class*='cookie-consent']",
        "[class*='gdpr-banner']",
        "[class*='consent-banner']",
        "[class*='privacy-banner']",
        "[id*='cookie-banner']",
        "[id*='cookie-notice']",
        "[id*='cookie-consent']",
        "[id*='gdpr-banner']",
        "[id*='consent-banner']",
        "[role='dialog'][class*='cookie']",
        "[role='alertdialog'][class*='cookie']",
    ])

    # =========================================================================
    # REJECT/DECLINE SELEKTOREN (für granulare Kontrolle)
    # =========================================================================

    reject_selectors: List[str] = field(default_factory=lambda: [
        # Deutsch
        "text=Ablehnen",
        "text=Nur notwendige",
        "text=Nur erforderliche",
        "text=Nur essenzielle",
        "text=Alle ablehnen",

        # Englisch
        "text=Reject All",
        "text=Reject",
        "text=Decline",
        "text=Only necessary",
        "text=Only essential",
        "text=Deny",

        # CSS-basiert
        "[id*='reject']",
        "[id*='decline']",
        "[class*='reject']",
        "[class*='decline']",
        "#onetrust-reject-all-handler",
        ".cky-btn-reject",
    ])

    # =========================================================================
    # SETTINGS/CUSTOMIZE SELEKTOREN
    # =========================================================================

    settings_selectors: List[str] = field(default_factory=lambda: [
        "text=Einstellungen",
        "text=Anpassen",
        "text=Cookie-Einstellungen",
        "text=Settings",
        "text=Customize",
        "text=Manage preferences",
        "text=Cookie settings",
        "#onetrust-pc-btn-handler",
        ".cky-btn-customize",
    ])

    def get_all_accept_selectors(self) -> List[str]:
        """Gibt alle Accept-Selektoren in priorisierter Reihenfolge zurück."""
        all_selectors = []

        # CMP-spezifische zuerst (höchste Trefferrate)
        all_selectors.extend(self.onetrust_selectors)
        all_selectors.extend(self.cookiebot_selectors)
        all_selectors.extend(self.borlabs_selectors)
        all_selectors.extend(self.complianz_selectors)
        all_selectors.extend(self.cookie_notice_selectors)
        all_selectors.extend(self.cookieyes_selectors)
        all_selectors.extend(self.usercentrics_selectors)
        all_selectors.extend(self.didomi_selectors)
        all_selectors.extend(self.quantcast_selectors)
        all_selectors.extend(self.iubenda_selectors)
        all_selectors.extend(self.klaro_selectors)
        all_selectors.extend(self.osano_selectors)
        all_selectors.extend(self.trustarc_selectors)
        all_selectors.extend(self.cookiescript_selectors)

        # Generische CSS-Selektoren
        all_selectors.extend(self.generic_css_selectors)

        # Text-basierte zuletzt (können false positives haben)
        all_selectors.extend(self.accept_text_patterns)

        return all_selectors

    def get_cmp_specific_selectors(self, cmp_name: str) -> List[str]:
        """Gibt Selektoren für eine spezifische CMP zurück."""
        cmp_mapping = {
            "onetrust": self.onetrust_selectors,
            "cookiebot": self.cookiebot_selectors,
            "borlabs": self.borlabs_selectors,
            "complianz": self.complianz_selectors,
            "cookienotice": self.cookie_notice_selectors,
            "cookieyes": self.cookieyes_selectors,
            "klaro": self.klaro_selectors,
            "osano": self.osano_selectors,
            "trustarc": self.trustarc_selectors,
            "usercentrics": self.usercentrics_selectors,
            "didomi": self.didomi_selectors,
            "quantcast": self.quantcast_selectors,
            "iubenda": self.iubenda_selectors,
            "cookiescript": self.cookiescript_selectors,
        }
        return cmp_mapping.get(cmp_name.lower(), [])


# Vordefinierte Cookie-Werte für bekannte CMPs
KNOWN_COOKIE_VALUES: Dict[str, Dict[str, str]] = {
    "onetrust": {
        "name": "OptanonAlertBoxClosed",
        "value": "2024-01-01T00:00:00.000Z",
    },
    "cookiebot": {
        "name": "CookieConsent",
        "value": "{stamp:'',necessary:true,preferences:true,statistics:true,marketing:true}",
    },
    "borlabs": {
        "name": "borlabs-cookie",
        "value": '{"consents":{"essential":true,"marketing":true,"statistics":true}}',
    },
    "complianz": {
        "name": "cmplz_consent_status",
        "value": "allow",
    },
    "gdpr": {
        "name": "cookie_consent",
        "value": "accepted",
    },
}
