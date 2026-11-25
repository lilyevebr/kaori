"""Runtime cleanup for the recovered storefront.

The HTML files remain an archival copy of the rendered Shopify pages.  The local
server calls ``prepare_html`` before serving them so obsolete commerce,
analytics, and checkout bootstraps do not make dead network requests.
"""

from __future__ import annotations

import re


SCRIPT_SRC_MARKERS = (
    "/checkouts/internal/preloads.js",
    "shop.app/checkouts/internal/preloads.js",
    "shopify.jsdeliver.cloud",
    "shopifycloud/shop-js/",
    "shopifycloud/storefront/",
    "shopifycloud/privacy-banner/",
    "/cdn/wpm/",
    "/web-pixels@",
    "shopifycloud/perf-kit/",
    "kaching-bundles",
    "zipify-oneclickupsell",
    "d1npnstlfekkfz.cloudfront.net/zipify",
    "consent-tracking-api",
    "insurance-widget.parcelwill.com",
    "cdn.shopify.com/storefront/standard-actions.js",
)

INLINE_SCRIPT_MARKERS = (
    'id="captcha-bootstrap"',
    'id="shopify-origin-trials"',
    "wpmLoader=function",
    "window.Shopify.webmcp",
    "shopify:webmcp_adapter_loaded",
    'data-source-attribution="shopify.dynamic_checkout.dynamic.init"',
    "window.ShopifyPaypalV4VisibilityTracking",
    "kachingBundlesAppEmbedLoaded",
    "TriplePixel",
    "function a0_0x2c6b",
)

LINK_MARKERS = (
    "/.well-known/ucp",
    "/buy/",
    "checkout-web/assets/",
    "type=\"application/json+oembed\"",
    "d1npnstlfekkfz.cloudfront.net/zipify",
    "kaching-bundles",
)

SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script\s*>", re.I | re.S)
LINK_RE = re.compile(r"<link\b[^>]*>", re.I | re.S)


def _keep_script(match: re.Match[str]) -> str:
    tag = match.group(0)
    lowered = tag.lower()
    if any(marker.lower() in lowered for marker in SCRIPT_SRC_MARKERS):
        return "<!-- Shopify/app runtime removed in local preview -->"
    if any(marker.lower() in lowered for marker in INLINE_SCRIPT_MARKERS):
        return "<!-- Shopify runtime removed in local preview -->"
    return tag


def _keep_link(match: re.Match[str]) -> str:
    tag = match.group(0)
    lowered = tag.lower()
    if any(marker.lower() in lowered for marker in LINK_MARKERS):
        return "<!-- Shopify checkout hint removed in local preview -->"
    return tag


def prepare_html(text: str) -> str:
    """Return the browser-safe local version without changing the archived file."""

    text = SCRIPT_RE.sub(_keep_script, text)
    text = LINK_RE.sub(_keep_link, text)

    # Keep every first-party image and navigation request inside the local mirror.
    for origin in (
        "https://www.try-kaori.com",
        "http://www.try-kaori.com",
        "//www.try-kaori.com",
        "https://try-kaori.com",
        "http://try-kaori.com",
        "//try-kaori.com",
    ):
        text = text.replace(origin, "")
    for origin in (
        r"https:\/\/www.try-kaori.com",
        r"http:\/\/www.try-kaori.com",
        r"\/\/www.try-kaori.com",
        r"https:\/\/try-kaori.com",
        r"http:\/\/try-kaori.com",
        r"\/\/try-kaori.com",
    ):
        text = text.replace(origin, "")

    # Two source handles kept German page labels even though the storefront is
    # English. Normalize their title, social metadata, and visible heading.
    text = text.replace("Kontakt", "Contact").replace("Startseite", "Home")

    # The original homepage contained one stale product handle that rendered a
    # captured Shopify 404 page. Point it at the live product copy instead.
    text = text.replace(
        "/products/deodorizing-persimmon-soap1",
        "/products/deodorizing-persimmon-soap",
    )

    config = '<script src="/storefront-config.js"></script>'
    runtime = '<script src="/local-mode.js" defer></script>'
    text = text.replace(runtime, "")
    if config not in text:
        text = text.replace("</body>", f"{config}\n{runtime}\n</body>")
    else:
        text = text.replace("</body>", f"{runtime}\n</body>")
    return text
