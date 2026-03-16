"""
Overlay Patterns - Selektoren für alle Arten von Störelementen

Kategorien:
- Newsletter-Popups
- Push-Notification-Dialoge
- Altersverifikation
- Werbe-Overlays
- Exit-Intent-Popups
- Social-Media-Widgets
- Chat-Widgets
"""

from dataclasses import dataclass, field
from typing import List, Dict
from enum import Enum


class OverlayType(Enum):
    """Typen von Overlay-Störelementen."""
    COOKIE_BANNER = "cookie_banner"
    NEWSLETTER = "newsletter"
    PUSH_NOTIFICATION = "push_notification"
    AGE_VERIFICATION = "age_verification"
    ADVERTISEMENT = "advertisement"
    EXIT_INTENT = "exit_intent"
    CHAT_WIDGET = "chat_widget"
    SOCIAL_WIDGET = "social_widget"
    FEEDBACK_WIDGET = "feedback_widget"
    GENERIC_MODAL = "generic_modal"
    STICKY_BANNER = "sticky_banner"


@dataclass
class OverlayPatterns:
    """Sammlung aller Overlay-Selektoren nach Kategorien."""

    # =========================================================================
    # NEWSLETTER POPUPS
    # =========================================================================

    newsletter_detection: List[str] = field(default_factory=lambda: [
        # Container-Erkennung
        "[class*='newsletter'][class*='popup']",
        "[class*='newsletter'][class*='modal']",
        "[class*='newsletter'][class*='overlay']",
        "[id*='newsletter'][id*='popup']",
        "[id*='newsletter'][id*='modal']",
        "[class*='subscribe'][class*='popup']",
        "[class*='subscribe'][class*='modal']",
        "[class*='email'][class*='popup']",
        "[class*='signup'][class*='modal']",
        ".newsletter-popup",
        ".newsletter-modal",
        "#newsletter-popup",
        "#newsletter-modal",
        "[data-newsletter-popup]",
        "[data-modal='newsletter']",
    ])

    newsletter_close: List[str] = field(default_factory=lambda: [
        # Schließen-Buttons
        "[class*='newsletter'] [class*='close']",
        "[class*='newsletter'] button[aria-label*='close' i]",
        "[class*='newsletter'] .close-btn",
        "[class*='newsletter'] .btn-close",
        "[id*='newsletter'] .close",
        "text=Nein danke",
        "text=Nein, danke",
        "text=No thanks",
        "text=No, thanks",
        "text=Nicht jetzt",
        "text=Später",
        "text=Maybe later",
        "text=Schließen",
        "[class*='newsletter'] button:has-text('×')",
        "[class*='newsletter'] button:has-text('X')",
    ])

    # =========================================================================
    # PUSH NOTIFICATION DIALOGE
    # =========================================================================

    push_notification_detection: List[str] = field(default_factory=lambda: [
        "[class*='push'][class*='notification']",
        "[class*='push'][class*='popup']",
        "[class*='notification'][class*='permission']",
        "[class*='web-push']",
        "[id*='push-notification']",
        "[class*='onesignal']",
        "[id*='onesignal']",
        ".push-prompt",
        "#push-prompt",
        "[data-push-notification]",
    ])

    push_notification_close: List[str] = field(default_factory=lambda: [
        "[class*='push'] [class*='close']",
        "[class*='push'] button[class*='deny']",
        "[class*='push'] button[class*='cancel']",
        "text=Nicht erlauben",
        "text=Blockieren",
        "text=Ablehnen",
        "text=Deny",
        "text=Block",
        "text=No thanks",
        "[class*='onesignal'] [class*='close']",
    ])

    # =========================================================================
    # ALTERSVERIFIKATION
    # =========================================================================

    age_verification_detection: List[str] = field(default_factory=lambda: [
        "[class*='age'][class*='verification']",
        "[class*='age'][class*='gate']",
        "[class*='age'][class*='check']",
        "[id*='age-verification']",
        "[id*='age-gate']",
        "[class*='adult'][class*='content']",
        "[data-age-gate]",
        "text=Bist du 18",
        "text=Are you 18",
        "text=Alter bestätigen",
    ])

    age_verification_confirm: List[str] = field(default_factory=lambda: [
        "[class*='age'] button:has-text('Ja')",
        "[class*='age'] button:has-text('Yes')",
        "[class*='age'] button:has-text('Bestätigen')",
        "[class*='age'] button:has-text('Confirm')",
        "[class*='age'] button:has-text('Ich bin 18')",
        "[class*='age'] button:has-text('Enter')",
        "text=Ja, ich bin 18",
        "text=Yes, I am 18",
        "text=Ich bin über 18",
    ])

    # =========================================================================
    # WERBE-OVERLAYS / PROMOTIONS
    # =========================================================================

    advertisement_detection: List[str] = field(default_factory=lambda: [
        "[class*='promo'][class*='popup']",
        "[class*='promo'][class*='modal']",
        "[class*='promo'][class*='overlay']",
        "[class*='offer'][class*='popup']",
        "[class*='offer'][class*='modal']",
        "[class*='discount'][class*='popup']",
        "[class*='sale'][class*='popup']",
        "[class*='coupon'][class*='popup']",
        "[class*='welcome'][class*='popup']",
        "[id*='promo-popup']",
        "[id*='offer-modal']",
        "[data-promo-popup]",
        ".interstitial-ad",
        "#interstitial",
    ])

    advertisement_close: List[str] = field(default_factory=lambda: [
        "[class*='promo'] [class*='close']",
        "[class*='offer'] [class*='close']",
        "[class*='discount'] [class*='close']",
        "[class*='promo'] button[aria-label*='close' i]",
        "text=Nicht interessiert",
        "text=Weiter ohne Angebot",
        "text=Skip",
        "text=Überspringen",
        "text=Continue without",
    ])

    # =========================================================================
    # EXIT INTENT POPUPS
    # =========================================================================

    exit_intent_detection: List[str] = field(default_factory=lambda: [
        "[class*='exit'][class*='intent']",
        "[class*='exit'][class*='popup']",
        "[class*='leaving'][class*='popup']",
        "[class*='dont-leave']",
        "[id*='exit-intent']",
        "[data-exit-intent]",
    ])

    exit_intent_close: List[str] = field(default_factory=lambda: [
        "[class*='exit'] [class*='close']",
        "[class*='exit'] button:has-text('×')",
        "text=Trotzdem verlassen",
        "text=Leave anyway",
    ])

    # =========================================================================
    # CHAT WIDGETS
    # =========================================================================

    chat_widget_detection: List[str] = field(default_factory=lambda: [
        # Bekannte Anbieter
        "[class*='intercom']",
        "#intercom-container",
        "[class*='drift']",
        "#drift-widget",
        "[class*='zendesk']",
        "[class*='tawk']",
        "#tawk-widget",
        "[class*='crisp']",
        "[class*='livechat']",
        "[class*='hubspot']",
        "[class*='freshchat']",
        "[class*='chat'][class*='widget']",
        "[class*='chat'][class*='bubble']",
        "[id*='chat-widget']",
        "[data-chat-widget]",
    ])

    chat_widget_close: List[str] = field(default_factory=lambda: [
        "[class*='chat'] [class*='close']",
        "[class*='chat'] [class*='minimize']",
        "[class*='intercom'] [class*='close']",
        "[class*='drift'] [class*='close']",
    ])

    # =========================================================================
    # FEEDBACK WIDGETS
    # =========================================================================

    feedback_widget_detection: List[str] = field(default_factory=lambda: [
        "[class*='feedback'][class*='widget']",
        "[class*='feedback'][class*='tab']",
        "[class*='survey'][class*='popup']",
        "[class*='nps'][class*='widget']",
        "[id*='feedback-widget']",
        "[data-feedback]",
        "[class*='hotjar']",
        "#_hj_feedback_container",
    ])

    feedback_widget_close: List[str] = field(default_factory=lambda: [
        "[class*='feedback'] [class*='close']",
        "[class*='survey'] [class*='close']",
        "text=Später",
        "text=Nicht jetzt",
    ])

    # =========================================================================
    # SOCIAL MEDIA WIDGETS
    # =========================================================================

    social_widget_detection: List[str] = field(default_factory=lambda: [
        "[class*='social'][class*='popup']",
        "[class*='social'][class*='modal']",
        "[class*='share'][class*='popup']",
        "[class*='follow'][class*='popup']",
        "[class*='like'][class*='popup']",
    ])

    social_widget_close: List[str] = field(default_factory=lambda: [
        "[class*='social'] [class*='close']",
        "[class*='share'] [class*='close']",
    ])

    # =========================================================================
    # STICKY BANNER (oben/unten festgeklebt)
    # =========================================================================

    sticky_banner_detection: List[str] = field(default_factory=lambda: [
        "[class*='sticky'][class*='banner']",
        "[class*='fixed'][class*='banner']",
        "[class*='notification'][class*='bar']",
        "[class*='announcement'][class*='bar']",
        "[class*='top-bar']",
        "[class*='bottom-bar']",
        "header + [style*='position: fixed']",
        "[style*='position: fixed'][style*='bottom: 0']",
    ])

    sticky_banner_close: List[str] = field(default_factory=lambda: [
        "[class*='sticky'] [class*='close']",
        "[class*='fixed'] [class*='dismiss']",
        "[class*='banner'] [class*='close']",
    ])

    # =========================================================================
    # GENERISCHE MODALE DIALOGE
    # =========================================================================

    generic_modal_detection: List[str] = field(default_factory=lambda: [
        ".modal.show",
        ".modal.active",
        ".modal.open",
        "[class*='modal'][class*='visible']",
        "[role='dialog'][aria-modal='true']",
        "[role='alertdialog']",
        ".overlay.active",
        ".overlay.visible",
        "[class*='lightbox'][class*='open']",
        ".fancybox-container",
        ".mfp-wrap",  # Magnific Popup
    ])

    generic_modal_close: List[str] = field(default_factory=lambda: [
        ".modal .close",
        ".modal .btn-close",
        ".modal [aria-label='Close']",
        "[role='dialog'] button[class*='close']",
        ".overlay .close",
        "button.close-modal",
        ".modal-close",
        # Escape-Taste wird separat behandelt
    ])

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def get_detection_selectors(self, overlay_type: OverlayType) -> List[str]:
        """Gibt Detection-Selektoren für einen Overlay-Typ zurück."""
        mapping = {
            OverlayType.NEWSLETTER: self.newsletter_detection,
            OverlayType.PUSH_NOTIFICATION: self.push_notification_detection,
            OverlayType.AGE_VERIFICATION: self.age_verification_detection,
            OverlayType.ADVERTISEMENT: self.advertisement_detection,
            OverlayType.EXIT_INTENT: self.exit_intent_detection,
            OverlayType.CHAT_WIDGET: self.chat_widget_detection,
            OverlayType.FEEDBACK_WIDGET: self.feedback_widget_detection,
            OverlayType.SOCIAL_WIDGET: self.social_widget_detection,
            OverlayType.STICKY_BANNER: self.sticky_banner_detection,
            OverlayType.GENERIC_MODAL: self.generic_modal_detection,
        }
        return mapping.get(overlay_type, [])

    def get_close_selectors(self, overlay_type: OverlayType) -> List[str]:
        """Gibt Close-Selektoren für einen Overlay-Typ zurück."""
        mapping = {
            OverlayType.NEWSLETTER: self.newsletter_close,
            OverlayType.PUSH_NOTIFICATION: self.push_notification_close,
            OverlayType.AGE_VERIFICATION: self.age_verification_confirm,
            OverlayType.ADVERTISEMENT: self.advertisement_close,
            OverlayType.EXIT_INTENT: self.exit_intent_close,
            OverlayType.CHAT_WIDGET: self.chat_widget_close,
            OverlayType.FEEDBACK_WIDGET: self.feedback_widget_close,
            OverlayType.SOCIAL_WIDGET: self.social_widget_close,
            OverlayType.STICKY_BANNER: self.sticky_banner_close,
            OverlayType.GENERIC_MODAL: self.generic_modal_close,
        }
        return mapping.get(overlay_type, [])

    def get_all_detection_selectors(self) -> Dict[OverlayType, List[str]]:
        """Gibt alle Detection-Selektoren zurück."""
        return {
            OverlayType.NEWSLETTER: self.newsletter_detection,
            OverlayType.PUSH_NOTIFICATION: self.push_notification_detection,
            OverlayType.AGE_VERIFICATION: self.age_verification_detection,
            OverlayType.ADVERTISEMENT: self.advertisement_detection,
            OverlayType.EXIT_INTENT: self.exit_intent_detection,
            OverlayType.CHAT_WIDGET: self.chat_widget_detection,
            OverlayType.FEEDBACK_WIDGET: self.feedback_widget_detection,
            OverlayType.SOCIAL_WIDGET: self.social_widget_detection,
            OverlayType.STICKY_BANNER: self.sticky_banner_detection,
            OverlayType.GENERIC_MODAL: self.generic_modal_detection,
        }
