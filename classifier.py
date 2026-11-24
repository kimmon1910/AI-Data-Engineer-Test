from typing import Any


PICKUP_KEYWORDS = (
    "กระบะ",
    "pickup",
    "hilux",
    "ranger",
    "d-max",
    "dmax",
    "navara",
    "triton",
    "bt-50",
    "colorado",
    "t60",
)
VAN_KEYWORDS = (
    "รถตู้",
    "van",
    "minibus",
    "commuter",
    "hiace",
    "h-1",
    "grand starex",
    "staria",
    "caravan",
    "urvan",
)
SUV_KEYWORDS = (
    "suv",
    "ppv",
    "crossover",
    "fortuner",
    "pajero",
    "mu-x",
    "mux",
    "everest",
    "cr-v",
    "hr-v",
    "cx-3",
    "cx-5",
    "cx-8",
    "corolla cross",
    "yaris cross",
    "x-trail",
    "x1",
    "x3",
    "x5",
)
NON_CATEGORY_VALUES = {"car", "upg", "deal"}


def classify_category(
    site_category: str | None,
    listing: dict[str, Any],
) -> str:
    """Prefer a real site category; otherwise classify from known car fields."""
    if site_category and site_category.strip():
        category = site_category.strip()
        if category.casefold() not in NON_CATEGORY_VALUES:
            return category

    searchable_fields = (
        "namemmt",
        "amodel",
        "model",
        "title",
        "abody",
        "atrim",
    )
    text = " ".join(str(listing.get(field, "")) for field in searchable_fields).casefold()

    if any(keyword in text for keyword in PICKUP_KEYWORDS):
        return "กระบะ"
    if any(keyword in text for keyword in VAN_KEYWORDS):
        return "รถตู้"
    if any(keyword in text for keyword in SUV_KEYWORDS):
        return "SUV/อื่น ๆ"
    return "เก๋ง"
