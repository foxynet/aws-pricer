"""Helpers for retrieving AWS Pricing and Savings Plans rates."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any, Final

import boto3

_PRICING_REGION: Final[str] = "us-east-1"
_EC2_SERVICE_CODE: Final[str] = "AmazonEC2"
_TERM_MATCH: Final[str] = "TERM_MATCH"
_ONDEMAND_KEY: Final[str] = "OnDemand"
_PRICE_DIMENSIONS_KEY: Final[str] = "priceDimensions"
_PRICE_PER_UNIT_KEY: Final[str] = "pricePerUnit"
_USD: Final[str] = "USD"
_NO_LICENSE_REQUIRED: Final[str] = "No License required"
_SUPPORTED_RATE_UNITS: Final[set[str]] = {"Hrs", "Hours"}
_SAVINGS_PLAN_DURATION_LABELS: Final[dict[int, str]] = {
    31_536_000: "1y",
    94_608_000: "3y",
}
_SAVINGS_PLAN_PRODUCT_DESCRIPTION_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "Linux": ("Linux/UNIX",),
    "Linux/UNIX": ("Linux/UNIX",),
}


_ONDEMAND_FILTERS: Final[tuple[tuple[str, str], ...]] = (
    ("tenancy", "Shared"),
    ("capacitystatus", "Used"),
    ("preInstalledSw", "NA"),
)


def get_ondemand_usd_per_hour(*, instance_type: str, region: str, os: str) -> Decimal:
    """Return the on-demand hourly USD price for an EC2 instance."""

    client = boto3.client("pricing", region_name=_PRICING_REGION)
    filters = [
        {"Type": _TERM_MATCH, "Field": "instanceType", "Value": instance_type},
        {"Type": _TERM_MATCH, "Field": "regionCode", "Value": region},
        {"Type": _TERM_MATCH, "Field": "operatingSystem", "Value": os},
        {"Type": _TERM_MATCH, "Field": "licenseModel", "Value": _NO_LICENSE_REQUIRED},
    ]
    filters.extend(
        {"Type": _TERM_MATCH, "Field": field, "Value": value}
        for field, value in _ONDEMAND_FILTERS
    )
    response = client.get_products(
        ServiceCode=_EC2_SERVICE_CODE,
        Filters=filters,
        MaxResults=1,
    )

    price_list = response.get("PriceList") or []
    for entry in price_list:
        try:
            price_item = _load_price_list_entry(entry)
        except (TypeError, json.JSONDecodeError) as exc:  # pragma: no cover - defensive
            raise ValueError("Invalid pricing payload returned by AWS Pricing API") from exc

        price = _extract_ondemand_usd(price_item)
        if price is not None:
            return price

    raise ValueError("No on-demand pricing data returned by AWS Pricing API")


def get_savingsplan_no_upfront_usd_per_hour(
    *,
    instance_type: str,
    region: str,
    os: str,
    plan_type: str,
    savingsPlanPaymentOptions: str | Iterable[str] = "No Upfront",
) -> dict[str, Decimal]:
    """Return 1-year and 3-year Savings Plans hourly USD prices."""

    client = boto3.client("savingsplans", region_name=_PRICING_REGION)
    product_descriptions = _savings_plan_product_descriptions(os)
    allowed_product_descriptions = set(product_descriptions)
    response = client.describe_savings_plans_offering_rates(
        savingsPlanPaymentOptions=_coerce_payment_options(savingsPlanPaymentOptions),
        savingsPlanTypes=[plan_type],
        filters=[
            {"name": "instanceType", "values": [instance_type]},
            {"name": "region", "values": [region]},
            {"name": "productDescription", "values": product_descriptions},
            {"name": "tenancy", "values": ["shared"]},
        ],
    )

    search_results = response.get("searchResults") or []
    rates: dict[str, Decimal] = {}
    for result in search_results:
        if not isinstance(result, Mapping):  # pragma: no cover - defensive
            continue

        usage_type = result.get("usageType")
        if not isinstance(usage_type, str) or "BoxUsage" not in usage_type:
            continue

        offering = result.get("savingsPlanOffering")
        if not isinstance(offering, Mapping):
            continue

        if offering.get("currency") != _USD:
            continue

        properties = result.get("properties")
        if isinstance(properties, Iterable):
            product_description = _extract_property_value(
                properties, "productDescription"
            )
            if (
                product_description is not None
                and product_description not in allowed_product_descriptions
            ):
                continue
        else:
            continue

        duration = offering.get("durationSeconds")
        if not isinstance(duration, int):
            continue

        label = _SAVINGS_PLAN_DURATION_LABELS.get(duration)
        if label is None:
            continue

        unit = result.get("unit")
        if isinstance(unit, str) and unit not in _SUPPORTED_RATE_UNITS:
            continue

        rate_value = result.get("rate")
        if not isinstance(rate_value, str):
            continue

        try:
            rate_decimal = Decimal(rate_value)
        except InvalidOperation as exc:  # pragma: no cover - defensive
            raise ValueError(f"Invalid Savings Plans rate '{rate_value}' returned by AWS") from exc

        current = rates.get(label)
        if current is None or rate_decimal < current:
            rates[label] = rate_decimal

    if {"1y", "3y"} - rates.keys():
        raise ValueError("Savings Plans rates for both 1y and 3y are required")

    return rates


def _load_price_list_entry(entry: Any) -> Mapping[str, Any]:
    if isinstance(entry, str):
        loaded = json.loads(entry)
    elif isinstance(entry, Mapping):
        loaded = entry
    else:  # pragma: no cover - defensive
        raise TypeError(f"Unexpected price list entry type: {type(entry)!r}")

    if not isinstance(loaded, Mapping):  # pragma: no cover - defensive
        raise TypeError("Decoded price list entry is not a mapping")

    return loaded


def _extract_ondemand_usd(price_item: Mapping[str, Any]) -> Decimal | None:
    terms = price_item.get("terms")
    if not isinstance(terms, Mapping):
        return None

    ondemand_terms = terms.get(_ONDEMAND_KEY)
    if not isinstance(ondemand_terms, Mapping):
        return None

    for term in ondemand_terms.values():
        if not isinstance(term, Mapping):
            continue

        dimensions = term.get(_PRICE_DIMENSIONS_KEY)
        if not isinstance(dimensions, Mapping):
            continue

        for dimension in dimensions.values():
            if not isinstance(dimension, Mapping):
                continue

            unit = dimension.get("unit")
            if isinstance(unit, str) and unit not in _SUPPORTED_RATE_UNITS:
                continue

            price_per_unit = dimension.get(_PRICE_PER_UNIT_KEY)
            if not isinstance(price_per_unit, Mapping):
                continue

            usd_value = price_per_unit.get(_USD)
            if not isinstance(usd_value, str):
                continue

            try:
                return Decimal(usd_value)
            except InvalidOperation as exc:  # pragma: no cover - defensive
                raise ValueError(
                    f"Invalid on-demand USD price '{usd_value}' returned by AWS"
                ) from exc

    return None


def _coerce_payment_options(value: str | Iterable[str]) -> list[str]:
    if isinstance(value, str):
        return [value]

    options = list(value)
    if not all(isinstance(option, str) for option in options):  # pragma: no cover - defensive
        raise TypeError("Savings Plan payment options must be strings")

    return options
def _savings_plan_product_descriptions(os: str) -> list[str]:
    aliases = _SAVINGS_PLAN_PRODUCT_DESCRIPTION_ALIASES.get(os)
    if aliases is None:
        return [os]

    # Use dict.fromkeys to preserve order while removing duplicates.
    return list(dict.fromkeys((os, *aliases)))


def _extract_property_value(
    properties: Iterable[Any],
    name: str,
) -> str | None:
    for prop in properties:
        if not isinstance(prop, Mapping):
            continue

        if prop.get("name") != name:
            continue

        value = prop.get("value")
        if isinstance(value, str):
            return value

    return None
