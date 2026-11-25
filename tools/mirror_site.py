#!/usr/bin/env python3
"""Create a local, editable static mirror of try-kaori.com.

Pages are rendered with the locally installed Chrome so JavaScript/Cloudflare can
complete normally. Public assets are then downloaded and references are rewritten
to local paths. This recovers the public storefront, not Shopify's private backend
or the original Liquid theme sources.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import html
from html.parser import HTMLParser
import json
import mimetypes
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from local_site import prepare_html, shopify_image_variant


ORIGIN = "https://try-kaori.com"
HOST = "try-kaori.com"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
PROFILE = Path(r"C:\Temp\KaoriChromeMirror")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site"

SEEDS = {
    "/",
    "/collections",
    "/collections/all",
    "/collections/best-sellers",
    "/collections/hair",
    "/pages/about-us",
    "/pages/contact",
    "/pages/refund-return-policy",
    "/policies/subscription-policy",
    "/policies/terms-of-service",
    "/policies/privacy-policy",
    "/policies/shipping-policy",
    "/policies/refund-policy",
    "/search",
}

PAGE_PREFIXES = ("/products/", "/collections/", "/pages/", "/policies/", "/blogs/")
SKIP_PAGE_PREFIXES = (
    "/cdn/", "/cart", "/checkout", "/checkouts/", "/account",
    "/customer_authentication/", "/apps/", "/a/", "/localization",
    "/services/", "/challenge", "/web-pixels", "/.well-known/",
)
TRACKER_HOSTS = {
    "connect.facebook.net", "www.googletagmanager.com", "www.clarity.ms",
    "scripts.clarity.ms", "static.klaviyo.com", "static-tracking.klaviyo.com",
    "scripts.conversion.io", "deltasteadco.com", "backend.alia-prod.com",
    "shopify.jsdeliver.cloud",
}
ASSET_EXTENSIONS = {
    ".css", ".js", ".mjs", ".png", ".jpg", ".jpeg", ".webp", ".gif",
    ".svg", ".avif", ".ico", ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp4", ".webm", ".mov", ".json", ".xml",
}


def log(message: str) -> None:
    print(message, flush=True)


def canonical(url: str, base: str = ORIGIN) -> str | None:
    url = html.unescape(url.strip())
    if not url or url.startswith(("#", "data:", "blob:", "javascript:", "mailto:", "tel:")):
        return None
    absolute = urljoin(base, url)
    p = urlsplit(absolute)
    if p.scheme not in ("http", "https"):
        return None
    # Fragments never affect the downloaded resource.
    return urlunsplit((p.scheme, p.netloc.lower(), p.path or "/", p.query, ""))


def clean_page_url(url: str) -> str | None:
    absolute = canonical(url)
    if not absolute:
        return None
    p = urlsplit(absolute)
    if p.hostname not in (HOST, f"www.{HOST}"):
        return None
    path = unquote(p.path or "/")
    if any(path.startswith(prefix) for prefix in SKIP_PAGE_PREFIXES):
        return None
    if path == "/" or path in ("/collections", "/search") or path.startswith(PAGE_PREFIXES):
        return ORIGIN + path.rstrip("/") if path != "/" else ORIGIN + "/"
    return None


def safe_segment(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).rstrip(" .") or "_"
    if len(value) > 120:
        suffix = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
        value = value[:100] + "-" + suffix
    if value.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        value = "_" + value
    return value


def page_path(url: str) -> Path:
    path = unquote(urlsplit(url).path).strip("/")
    if not path:
        return OUT / "index.html"
    parts = [safe_segment(p) for p in path.split("/") if p]
    return OUT.joinpath(*parts, "index.html")


def asset_path(url: str) -> Path:
    p = urlsplit(url)
    parts = [safe_segment(unquote(x)) for x in p.path.split("/") if x]
    if not parts or p.path.endswith("/"):
        parts.append("index")
    if p.hostname not in (HOST, f"www.{HOST}"):
        parts = ["_external", safe_segment(p.netloc)] + parts
    variant = shopify_image_variant("/" + "/".join(parts), p.query)
    if variant:
        return OUT / variant.lstrip("/")
    return OUT.joinpath(*parts)


def local_url(url: str) -> str:
    return "/" + asset_path(url).relative_to(OUT).as_posix()


class Extractor(HTMLParser):
    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.pages: set[str] = set()
        self.assets: set[str] = set()

    def add_asset(self, value: str) -> None:
        url = canonical(value, self.base)
        if url:
            self.assets.add(url)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {k.lower(): v for k, v in attrs if v is not None}
        if tag == "a" and "href" in data:
            page = clean_page_url(urljoin(self.base, data["href"]))
            if page:
                self.pages.add(page)

        if tag in ("img", "script", "iframe", "source", "video", "audio", "embed"):
            for attr in ("src", "data-src", "data-lazy-src", "poster"):
                if data.get(attr):
                    self.add_asset(data[attr])
        if tag == "object" and data.get("data"):
            self.add_asset(data["data"])
        if tag == "link" and data.get("href"):
            rel = data.get("rel", "").lower()
            if any(x in rel for x in ("stylesheet", "icon", "preload", "modulepreload", "manifest")):
                self.add_asset(data["href"])
        for attr in ("srcset", "data-srcset"):
            if data.get(attr):
                for candidate in data[attr].split(","):
                    candidate = candidate.strip().split()[0] if candidate.strip() else ""
                    if candidate:
                        self.add_asset(candidate)
        if data.get("style"):
            for raw in css_urls(data["style"]):
                self.add_asset(raw)


def css_urls(text: str) -> Iterable[str]:
    pattern = r"(?:url\(\s*|@import\s+)(?:['\"])?([^'\"\)\s;]+)"
    for match in re.finditer(pattern, text, flags=re.I):
        yield match.group(1)


def chrome_dump(url: str, budget_ms: int = 7000) -> str:
    PROFILE.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(CHROME), "--headless=new", "--disable-gpu", "--no-first-run",
        "--no-default-browser-check", "--disable-background-networking",
        f"--user-data-dir={PROFILE}", f"--virtual-time-budget={budget_ms}",
        "--dump-dom", url,
    ]
    for attempt in range(3):
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=45)
        except subprocess.TimeoutExpired:
            if attempt == 2:
                raise
            time.sleep(2)
            continue
        text = proc.stdout.decode("utf-8", "replace")
        if proc.returncode == 0 and len(text) > 200 and "Verifying your connection" not in text:
            return text.replace("\r\n", "\n")
        if attempt == 2:
            error = proc.stderr.decode("utf-8", "replace")[-1000:]
            raise RuntimeError(f"Chrome failed for {url}: code={proc.returncode} {error}")
        time.sleep(2 + attempt)
    raise RuntimeError(f"Chrome failed for {url}")


def api_handles(endpoint: str, key: str) -> list[str]:
    try:
        doc = chrome_dump(ORIGIN + endpoint, budget_ms=2500)
        match = re.search(r"<pre[^>]*>(.*)</pre>", doc, flags=re.I | re.S)
        if not match:
            return []
        data = json.loads(html.unescape(match.group(1)))
        return [item["handle"] for item in data.get(key, []) if item.get("handle")]
    except Exception as exc:
        log(f"  aviso: catálogo {endpoint} não pôde ser lido: {exc}")
        return []


def should_download(url: str) -> bool:
    p = urlsplit(url)
    host = p.hostname or ""
    if host in TRACKER_HOSTS:
        return False
    ext = Path(unquote(p.path)).suffix.lower()
    if ext in ASSET_EXTENSIONS:
        return True
    if host in (HOST, f"www.{HOST}") and p.path.startswith("/cdn/"):
        return True
    if host in ("fonts.googleapis.com", "fonts.gstatic.com", "cdn.shopify.com"):
        return True
    return False


def request_bytes(url: str) -> tuple[bytes, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/158.0 Safari/537.36",
        "Accept": "*/*",
        "Referer": ORIGIN + "/",
    }
    request = Request(url, headers=headers)
    with urlopen(request, timeout=40) as response:
        return response.read(), response.headers.get_content_type()


def download_one(url: str) -> tuple[str, bool, str, set[str]]:
    target = asset_path(url)
    nested: set[str] = set()
    try:
        data, content_type = request_bytes(url)
        if target.parent.name == "_image-variants" and not content_type.startswith("image/"):
            return url, False, f"unexpected media type: {content_type}", nested
        target.parent.mkdir(parents=True, exist_ok=True)
        if content_type == "text/css" or target.suffix.lower() == ".css":
            text = data.decode("utf-8", "replace")
            for raw in css_urls(text):
                child = canonical(raw, url)
                if child and should_download(child):
                    nested.add(child)
                    text = text.replace(raw, local_url(child))
            data = text.encode("utf-8")
        target.write_bytes(data)
        return url, True, f"{len(data)} bytes", nested
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return url, False, str(exc), nested


def disable_trackers(text: str) -> str:
    for host in TRACKER_HOSTS:
        pattern = rf"<script\b[^>]*\bsrc=['\"][^'\"]*{re.escape(host)}[^'\"]*['\"][^>]*>\s*</script>"
        text = re.sub(pattern, f"<!-- rastreador externo removido do backup local: {host} -->", text, flags=re.I)
    return text


def rewrite_page(text: str, assets: Iterable[str]) -> str:
    text = disable_trackers(text)
    # Longest first prevents a short URL from replacing the prefix of a longer one.
    for url in sorted(set(assets), key=len, reverse=True):
        if should_download(url):
            target = local_url(url)
            text = text.replace(url, target).replace(html.escape(url, quote=True), html.escape(target, quote=True))
    text = text.replace("https://www.try-kaori.com", "").replace(ORIGIN, "")
    return prepare_html(text)


def write_local_support() -> None:
    shutil.copyfile(ROOT / "overrides" / "storefront-config.js", OUT / "storefront-config.js")
    shutil.copyfile(ROOT / "overrides" / "local-mode.js", OUT / "local-mode.js")


def repair_images() -> int:
    """Restore image variants discarded by earlier versions of the mirror."""
    manifest = json.loads((ROOT / "backup-manifest.json").read_text(encoding="utf-8"))
    files: dict[Path, str] = {}
    for item in manifest["assets"]:
        url = item["url"]
        target = asset_path(url)
        if target.parent.name != "_image-variants":
            continue
        files[target] = url
        # Older pages also reference the shared filename without a size query.
        # Keep the source image at that path for those references.
        image = urlsplit(url)
        parameters = [(key, value) for key, value in parse_qsl(image.query) if key == "v"]
        original = image._replace(query=urlencode(parameters)).geturl()
        files[asset_path(original)] = original

    pending = [
        url for path, url in files.items()
        if path.parent.name != "_image-variants" or not path.is_file()
    ]
    log(f"Restaurando {len(pending)} arquivos de imagem de {len(files)} identificados...")
    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for count, (url, ok, detail, _) in enumerate(pool.map(download_one, pending), 1):
            if not ok:
                failures += 1
                log(f"  falha: {url} ({detail})")
            if count % 100 == 0 or count == len(pending):
                log(f"  {count}/{len(pending)} processados")
    log(f"Concluído: {len(pending) - failures} arquivos restaurados, {failures} falhas.")
    return int(bool(failures))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=120)
    parser.add_argument("--repair-images", action="store_true")
    args = parser.parse_args()
    if args.repair_images:
        return repair_images()
    if not CHROME.exists():
        raise SystemExit(f"Chrome não encontrado em {CHROME}")
    OUT.mkdir(parents=True, exist_ok=True)
    write_local_support()

    queue = {ORIGIN + path for path in SEEDS}
    products = api_handles("/products.json?limit=250", "products")
    collections = api_handles("/collections.json?limit=250", "collections")
    queue.update(f"{ORIGIN}/products/{handle}" for handle in products)
    queue.update(f"{ORIGIN}/collections/{handle}" for handle in collections)
    log(f"Catálogo: {len(products)} produtos, {len(collections)} coleções")

    visited: set[str] = set()
    pages: dict[str, dict] = {}
    all_assets: set[str] = set()
    failures: list[dict] = []

    while queue and len(visited) < args.max_pages:
        url = sorted(queue)[0]
        queue.remove(url)
        if url in visited:
            continue
        visited.add(url)
        log(f"Página {len(visited):02d}: {url}")
        try:
            text = chrome_dump(url)
        except Exception as exc:
            failures.append({"url": url, "kind": "page", "error": str(exc)})
            log(f"  falhou: {exc}")
            continue
        extractor = Extractor(url)
        extractor.feed(text)
        queue.update(p for p in extractor.pages if p not in visited)
        all_assets.update(a for a in extractor.assets if should_download(a))
        pages[url] = {"html": text, "assets": sorted(extractor.assets), "links": sorted(extractor.pages)}
        log(f"  links={len(extractor.pages)} ativos={len(extractor.assets)}")

    log(f"Baixando {len(all_assets)} ativos públicos...")
    downloaded: set[str] = set()
    pending = set(all_assets)
    asset_results: list[dict] = []
    while pending:
        batch = sorted(pending - downloaded)
        pending.clear()
        if not batch:
            break
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            for url, ok, detail, nested in pool.map(download_one, batch):
                downloaded.add(url)
                pending.update(x for x in nested if x not in downloaded)
                asset_results.append({"url": url, "ok": ok, "detail": detail, "path": local_url(url)})
                if not ok:
                    failures.append({"url": url, "kind": "asset", "error": detail})
        all_assets.update(pending)

    for url, data in pages.items():
        output = page_path(url)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rewrite_page(data["html"], data["assets"]), encoding="utf-8")

    manifest = {
        "source": ORIGIN,
        "created_local": time.strftime("%Y-%m-%d %H:%M:%S"),
        "scope": "public storefront static mirror",
        "pages": [{"url": url, "path": "/" + page_path(url).relative_to(OUT).as_posix()} for url in sorted(pages)],
        "assets": asset_results,
        "failures": failures,
        "catalog": {"products": products, "collections": collections},
    }
    (ROOT / "backup-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Concluído: {len(pages)} páginas, {sum(1 for a in asset_results if a['ok'])} ativos, {len(failures)} falhas")
    return 0 if pages else 1


if __name__ == "__main__":
    raise SystemExit(main())
