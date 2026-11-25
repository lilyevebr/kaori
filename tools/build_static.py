"""Build the offline storefront as static files for Vercel."""

from html import unescape
from pathlib import Path
import re
import shutil
from urllib.parse import unquote

from tools.local_site import prepare_html, shopify_image_variant
from serve_local import KaoriHandler


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "site"
OUTPUT = ROOT / "dist"
OLD_PRODUCT_ROUTE = Path("products/deodorizing-persimmon-soap1/index.html")
IMAGE_URL = re.compile(
    r"""(?<![\w./-])(?P<path>/(?:cdn/shop/files/|_external/cdn\.shopify\.com/s/files/)[^\s"'<>?]+)"""
    r"""\?(?P<query>[^\s"'<>#,)]+)"""
)


def use_static_image(match: re.Match[str]) -> str:
    path = unquote(match["path"])
    variant = shopify_image_variant(path, unescape(match["query"]))
    if variant and (SOURCE / variant.lstrip("/")).is_file():
        return variant
    return match[0]


def build() -> None:
    if OUTPUT.is_symlink() or OUTPUT.resolve() != ROOT / "dist":
        raise RuntimeError("The build output must be the dist directory in this project.")
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)

    page_count = 0
    for source in SOURCE.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(SOURCE)
        if relative == OLD_PRODUCT_ROUTE or relative.parts[0].startswith("web-pixels@"):
            continue
        if relative.name == "index.html":
            # Vercel's clean URLs serve products/item.html at /products/item.
            destination = OUTPUT / relative
            if relative.parent != Path("."):
                route = OUTPUT / relative.parent
                destination = route.with_name(route.name + ".html")
            destination.parent.mkdir(parents=True, exist_ok=True)
            page = prepare_html(source.read_text(encoding="utf-8"))
            destination.write_text(IMAGE_URL.sub(use_static_image, page), encoding="utf-8")
            page_count += 1
        else:
            destination = OUTPUT / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)

    for name in ("local-mode.js", "storefront-config.js"):
        shutil.copyfile(ROOT / "overrides" / name, OUTPUT / name)

    for url, fallback in KaoriHandler.font_fallbacks.items():
        destination = OUTPUT / url.lstrip("/")
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / fallback, destination)

    if not (OUTPUT / "index.html").is_file():
        raise RuntimeError("The static homepage is missing.")
    print(f"Built {page_count} storefront pages in {OUTPUT}")


if __name__ == "__main__":
    build()
