import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any

import requests

from classifier import classify_category
from image_quality import calculate_image_quality
from scraper import (
    build_detail_url,
    download_images,
    extract_mileage,
    extract_price_from_detail,
    extract_photo_urls,
    fetch_ad_detail,
    fetch_listing_records,
)


LOGGER = logging.getLogger(__name__)
SITE_CATEGORY_FIELDS = ("category", "category_name", "vehicle_category", "body_type")


def parse_integer(value: Any) -> int | None:
    """Convert a price, year, or mileage string to an integer."""
    if value is None:
        return None
    match = re.search(r"\d[\d,]*", str(value))
    if not match:
        return None
    try:
        return int(match.group(0).replace(",", ""))
    except ValueError:
        return None


def find_site_category(listing: dict[str, Any]) -> str | None:
    for field in SITE_CATEGORY_FIELDS:
        value = listing.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def create_car_record(
    listing: dict[str, Any],
    detail_soup: Any | None,
    detail_url: str,
) -> dict[str, Any]:
    price = parse_integer(listing.get("prc"))
    if price is None and detail_soup is not None:
        price = extract_price_from_detail(detail_soup)

    mileage = extract_mileage(detail_soup) if detail_soup is not None else None
    model = listing.get("amodel") or listing.get("model") or listing.get("namemmt")
    category = classify_category(find_site_category(listing), listing)

    return {
        "ad_id": str(listing.get("cid", "")),
        "brand": listing.get("amake") or None,
        "model": str(model).strip() if model else None,
        "year": parse_integer(listing.get("yr4")),
        "price": price,
        "mileage": mileage,
        "category": category,
        "source_url": detail_url,
        "images": [],
    }


def process_ads(
    listings: list[dict[str, Any]],
    image_dir: Path,
    delay: float,
) -> list[dict[str, Any]]:
    from scraper import create_http_session

    session = create_http_session()
    cars = []

    try:
        for index, listing in enumerate(listings, start=1):
            ad_id = str(listing.get("cid", "")).strip()
            LOGGER.info("Processing ad %s/%s", index, len(listings))
            detail_url = build_detail_url(listing)
            detail_soup = None

            try:
                detail_soup = fetch_ad_detail(session, detail_url, delay)
            except (requests.RequestException, ValueError) as error:
                LOGGER.warning("Could not load ad %s: %s", ad_id, error)

            car = create_car_record(listing, detail_soup, detail_url)
            if detail_soup is not None:
                image_urls = extract_photo_urls(detail_soup, detail_url)
            else:
                image_urls = [listing.get("img")] if listing.get("img") else []

            downloaded = download_images(
                session=session,
                ad_id=ad_id,
                image_urls=image_urls,
                image_dir=image_dir,
                delay=delay,
            )

            for photo in downloaded:
                try:
                    photo["quality_score"] = calculate_image_quality(photo["path"])
                    LOGGER.info("Image quality: %s", photo["quality_score"])
                    car["images"].append(photo)
                except (OSError, ValueError) as error:
                    LOGGER.warning("Could not score image %s: %s", photo["path"], error)

            cars.append(car)
    finally:
        session.close()

    return cars


def save_cars(cars: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(cars, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")
    LOGGER.info("Saved %s", output_path.as_posix())


def positive_limit(value: str) -> int:
    limit = int(value)
    if not 1 <= limit <= 100:
        raise argparse.ArgumentTypeError("limit must be between 1 and 100")
    return limit


def positive_delay(value: str) -> float:
    delay = float(value)
    if delay <= 0:
        raise argparse.ArgumentTypeError("delay must be greater than zero")
    return delay


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Taladrod used-car listings.")
    parser.add_argument("--limit", type=positive_limit, default=100, help="Ads to collect (1-100)")
    parser.add_argument("--delay", type=positive_delay, default=1.0, help="Seconds between requests")
    parser.add_argument("--output", type=Path, default=Path("output/cars.json"))
    parser.add_argument("--images-dir", type=Path, default=Path("images"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

    from scraper import create_http_session

    session = create_http_session()
    try:
        listings = fetch_listing_records(session, args.limit, args.delay)
    except Exception as error:
        LOGGER.error("Could not read the listing page: %s", error)
        raise SystemExit(1) from error
    finally:
        session.close()

    LOGGER.info("Found %s listings to process", len(listings))
    args.images_dir.mkdir(parents=True, exist_ok=True)
    cars = process_ads(listings, args.images_dir, args.delay)
    save_cars(cars, args.output)


if __name__ == "__main__":
    main()
