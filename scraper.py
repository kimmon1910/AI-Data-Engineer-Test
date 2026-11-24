import json
import logging
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


LISTING_URL = "https://www.taladrod.com/w40/isch/schc.aspx?fno:new"
LISTING_BATCH_SIZE = 10
MAX_ADS_PER_RUN = 100
REQUEST_TIMEOUT = 20
RETRIES = 3

# These selectors were checked against the live listing and detail HTML.
DETAIL_IMAGE_SELECTORS = (
    "#left_sub img[src*='/cidx/']",
    "#cdImgCarLowerContainer img.cdImgCar",
)

LOGGER = logging.getLogger(__name__)


def create_http_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
            "image/webp,*/*;q=0.8",
            "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.taladrod.com/",
        }
    )
    retry = Retry(
        total=RETRIES,
        connect=RETRIES,
        read=RETRIES,
        status=RETRIES,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


def get_with_retry(
    session: requests.Session,
    url: str,
    delay: float = 1.0,
) -> requests.Response:
    if delay:
        time.sleep(delay)
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response


def parse_listing_data(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    decoder = json.JSONDecoder()

    for script in soup.find_all("script"):
        script_text = script.string or script.get_text()
        match = re.search(r"\bSchDataJSON\s*=\s*", script_text)
        if not match:
            continue
        try:
            data, _ = decoder.raw_decode(script_text, match.end())
        except json.JSONDecodeError as error:
            raise ValueError("Could not parse the listing data embedded in the page") from error
        cars = data.get("cars") if isinstance(data, dict) else None
        if not isinstance(cars, list):
            raise ValueError("The embedded listing data does not contain a cars list")
        return [car for car in cars if isinstance(car, dict)]

    raise ValueError("The live page no longer contains the expected SchDataJSON data")


def build_detail_url(listing: dict[str, Any]) -> str:
    ad_id = str(listing.get("cid", "")).strip()
    if not ad_id:
        raise ValueError("A listing is missing its ad ID (cid)")
    detail_url = urljoin(LISTING_URL, f"../icar/cardet.aspx?cid={ad_id}")
    if listing.get("cbt") != "Baht" and listing.get("dpmt"):
        detail_url += f"&dpmt={listing['dpmt']}"
    return detail_url


def fetch_listing_records(
    session: requests.Session,
    limit: int = 100,
    delay: float = 1.0,
) -> list[dict[str, Any]]:
    if not 1 <= limit <= MAX_ADS_PER_RUN:
        raise ValueError(f"limit must be between 1 and {MAX_ADS_PER_RUN}")

    response = get_with_retry(session, LISTING_URL, delay)
    all_cars = parse_listing_data(response.text)
    selected = []
    seen_urls = set()

    # Taladrod embeds all matching records in the response; its JavaScript
    # presents them in batches of 10 while scrolling.
    for page_start in range(0, len(all_cars), LISTING_BATCH_SIZE):
        page = all_cars[page_start : page_start + LISTING_BATCH_SIZE]
        LOGGER.info("Reading listing batch %s", page_start // LISTING_BATCH_SIZE + 1)
        for listing in page:
            try:
                detail_url = build_detail_url(listing)
            except ValueError as error:
                LOGGER.warning("Skipping a listing without an ad ID: %s", error)
                continue
            if detail_url in seen_urls:
                LOGGER.warning("Skipping duplicate listing URL: %s", detail_url)
                continue
            seen_urls.add(detail_url)
            selected.append(listing)
            if len(selected) >= limit:
                return selected

    return selected


def fetch_ad_detail(
    session: requests.Session,
    detail_url: str,
    delay: float = 1.0,
) -> BeautifulSoup:
    response = get_with_retry(session, detail_url, delay)
    return BeautifulSoup(response.text, "html.parser")


def extract_photo_urls(soup: BeautifulSoup, page_url: str) -> list[str]:
    urls = []
    seen_urls = set()

    for selector in DETAIL_IMAGE_SELECTORS:
        for image in soup.select(selector):
            source = image.get("src") or image.get("data-src")
            if not source:
                continue
            image_url = urljoin(page_url, source.strip())
            if image_url not in seen_urls:
                seen_urls.add(image_url)
                urls.append(image_url)

    return urls


def extract_mileage(soup: BeautifulSoup) -> int | None:
    # The detail page's summary contains the structured "เลขไมล์" label.
    for element in soup.select("div.txt"):
        text = element.get_text(" ", strip=True)
        match = re.search(r"เลขไมล์\s*[:：]?\s*([\d,]+)", text, re.IGNORECASE)
        if match:
            return int(match.group(1).replace(",", ""))
    return None


def extract_price_from_detail(soup: BeautifulSoup) -> int | None:
    price_element = soup.select_one("#xPrice")
    if price_element is None:
        return None
    match = re.search(r"\d[\d,]*", price_element.get_text(" ", strip=True))
    return int(match.group(0).replace(",", "")) if match else None


def image_extension(url: str, content_type: str) -> str:
    extension = Path(urlsplit(url).path).suffix.lower()
    if extension in {".jpg", ".jpeg", ".png", ".webp"}:
        return extension
    mime_extension = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    return mime_extension.get(content_type.split(";", 1)[0].lower(), ".jpg")


def download_images(
    session: requests.Session,
    ad_id: str,
    image_urls: list[str],
    image_dir: Path,
    delay: float = 1.0,
) -> list[dict[str, str]]:
    downloaded = []
    seen_urls = set()
    safe_ad_id = re.sub(r"[^A-Za-z0-9_-]", "_", ad_id)

    for image_url in image_urls:
        if not image_url or image_url in seen_urls:
            continue
        seen_urls.add(image_url)
        image_number = len(downloaded) + 1

        try:
            response = get_with_retry(session, image_url, delay)
            if not response.content:
                raise ValueError("The image response was empty")

            extension = image_extension(image_url, response.headers.get("Content-Type", ""))
            image_path = image_dir / f"{safe_ad_id}_{image_number:02d}{extension}"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(response.content)
            downloaded.append(
                {
                    "path": image_path.as_posix(),
                    "source_url": image_url,
                }
            )
            LOGGER.info("Downloaded image %s/%s", image_number, len(image_urls))
        except (requests.RequestException, OSError, ValueError) as error:
            LOGGER.warning("Failed to download image %s: %s", image_url, error)

    return downloaded
