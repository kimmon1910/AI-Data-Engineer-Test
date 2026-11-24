# Taladrod Used-Car Scraper

A small Python program that collects used-car listings and their photos from Taladrod, assigns a simple vehicle category, and scores each downloaded photo with local classical computer vision.

## Project structure

```text
AI-Data-Engineer-Test/
├── main.py
├── scraper.py
├── image_quality.py
├── classifier.py
├── requirements.txt
├── README.md
├── images/
└── output/
    └── cars.json
```

## Install

Use Python 3.10 or later:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## Run

```bash
python main.py
```

The default run selects up to the first 100 unique ads in the order returned by the listing page. To choose a smaller number or change the request delay:

```bash
python main.py --limit 20 --delay 1.5
```

The limit must be between 1 and 100, and the request delay must be greater than zero. JSON is written to `output/cars.json`; downloaded photos go into `images/`. Both paths can be changed:

```bash
python main.py --limit 10 --output output/sample.json --images-dir images
```

The live listing HTML was inspected before writing the scraper. It embeds its records in `var SchDataJSON={"cars":[...]}`. The site's JavaScript displays these records in batches of 10 as the user scrolls; the scraper reads those batches from the embedded data instead of making unnecessary page requests. The detail page uses `icar/cardet.aspx?cid=...`. Photo selectors are kept together in `scraper.py`: `#left_sub img[src*='/cidx/']` and `#cdImgCarLowerContainer img.cdImgCar`. This page serves the listing and detail data in HTML, so Playwright is not needed.

## Retry and request delay

Each GET request has a 20-second timeout and up to three retries for network errors and HTTP 429/5xx responses, with an increasing backoff. The default one-second delay is applied between requests to avoid sending them too quickly. A failed ad or photo is logged and skipped; other ads continue.

## Vehicle categories

The scraper uses an explicit category field if one is present in the site's listing data. The current inspected records do not expose a category field, so `classifier.py` applies readable keyword rules to the listing's make/model/title. It checks for pickup and van terms first, then SUV/crossover terms, and otherwise uses `เก๋ง`. The site's generic record field `type: "car"` is not treated as a vehicle category.

## Image quality

`image_quality.py` uses OpenCV only; it does not call an external AI service or use a trained model. Each component is normalized to 0–10, then combined:

- Sharpness: Laplacian variance, scaled to 0–10 (60%).
- Brightness: grayscale mean, scoring highest near mid-gray and lower near very dark or very bright (25%).
- Resolution: image pixel count relative to 1280 × 720, capped at 10 (15%).

This classical-computer-vision approach is fast, runs locally, has no per-image API cost, and makes the score easy to explain. It is a useful heuristic, not a human-quality judgment: composition, subject visibility, and vehicle condition are not assessed.

## Example JSON

```json
[
  {
    "ad_id": "123456",
    "brand": "Toyota",
    "model": "Yaris",
    "year": 2020,
    "price": 459000,
    "mileage": 65000,
    "category": "เก๋ง",
    "source_url": "https://www.taladrod.com/w40/icar/cardet.aspx?cid=123456",
    "images": [
      {
        "path": "images/123456_01.jpg",
        "source_url": "https://imgc2.taladrod.com/c/cidx/example_1.jpg",
        "quality_score": 8.5
      }
    ]
  }
]
```

Unavailable price or mileage is written as `null`. Only successfully downloaded and readable photos are included in `images`; their source URLs are deduplicated.

## Limitations

- The site's HTML and photo selectors can change; update the centralized selectors in `scraper.py` if that happens.
- Category rules are heuristic and may need new model keywords.
- Image scores measure sharpness, brightness, and pixel resolution only, not composition or semantic quality.
- A listing removed or changed between collection and detail-page requests may have incomplete fields or no photos.
- The program intentionally makes requests sequentially and can take time when collecting many ads and photos. Follow the site's terms and access policies when running it.

## Interview walkthrough

1. `scraper.py` reads the listing JSON embedded in the page, keeps the first unique ads up to the requested limit, fetches each detail page, and downloads distinct photos. Retry, timeout, delay, and per-item error handling are in this file.
2. `classifier.py` first honors an explicit site category, then uses a short list of transparent keyword rules.
3. `image_quality.py` computes the three OpenCV metrics and combines their normalized scores with the documented weights.
4. `main.py` coordinates those steps, keeps one bad ad or photo from stopping the run, and writes the final JSON.

The design favors a small number of readable functions and local processing, with no database, browser automation, cloud service, or external vision API.
