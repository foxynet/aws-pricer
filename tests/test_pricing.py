from __future__ import annotations

import types
from decimal import Decimal
from typing import Any

import pytest

from aws_pricer import pricing
from tests.fixtures import pricing as pricing_fixtures


class DummyPricingClient:
    def __init__(self, response: dict[str, Any]):
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def get_products(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.response


class DummySavingsPlansClient:
    def __init__(self, response: dict[str, Any]):
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def describe_savings_plans_offering_rates(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.response


def _patch_boto3(monkeypatch: pytest.MonkeyPatch, fake_client: Any) -> None:
    """Patch the boto3 module used in aws_pricer.pricing."""

    def _client(service_name: str, *, region_name: str | None = None) -> Any:
        return fake_client(service_name=service_name, region_name=region_name)

    monkeypatch.setattr(
        pricing,
        "boto3",
        types.SimpleNamespace(client=_client),
        raising=False,
    )


def test_get_ondemand_usd_per_hour_fetches_hourly_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    if not hasattr(pricing, "get_ondemand_usd_per_hour"):
        pytest.fail("pricing.get_ondemand_usd_per_hour is not implemented")

    price_list_entry = pricing_fixtures.make_price_list_entry(usd_per_hour="0.096")
    response = {"PriceList": [price_list_entry], "FormatVersion": "aws_v1"}
    client = DummyPricingClient(response=response)

    def _fake_client(service_name: str, region_name: str | None = None) -> DummyPricingClient:
        assert service_name == "pricing"
        assert region_name == "us-east-1"
        return client

    _patch_boto3(monkeypatch, fake_client=_fake_client)

    result = pricing.get_ondemand_usd_per_hour(
        instance_type="m6i.large",
        region="ap-southeast-2",
        os="Linux",
    )

    assert result == Decimal("0.096")
    assert client.calls, "Expected aws_pricer.pricing to invoke get_products"
    call_kwargs = client.calls[-1]

    assert call_kwargs.get("ServiceCode") == "AmazonEC2"
    filters = {(
        filter_entry.get("Field"),
        filter_entry.get("Type"),
    ): filter_entry.get("Value") for filter_entry in call_kwargs.get("Filters", [])}
    assert filters[("instanceType", "TERM_MATCH")] == "m6i.large"
    assert filters[("regionCode", "TERM_MATCH")] == "ap-southeast-2"
    assert filters[("operatingSystem", "TERM_MATCH")] == "Linux"
    assert filters[("licenseModel", "TERM_MATCH")] == "No License required"
    assert filters[("tenancy", "TERM_MATCH")] == "Shared"
    assert filters[("capacitystatus", "TERM_MATCH")] == "Used"
    assert filters[("preInstalledSw", "TERM_MATCH")] == "NA"
    assert call_kwargs.get("MaxResults") == 1


def test_get_ondemand_usd_per_hour_errors_when_no_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    if not hasattr(pricing, "get_ondemand_usd_per_hour"):
        pytest.fail("pricing.get_ondemand_usd_per_hour is not implemented")

    client = DummyPricingClient(response={"PriceList": [], "FormatVersion": "aws_v1"})

    def _fake_client(service_name: str, region_name: str | None = None) -> DummyPricingClient:
        assert service_name == "pricing"
        assert region_name == "us-east-1"
        return client

    _patch_boto3(monkeypatch, fake_client=_fake_client)

    with pytest.raises(ValueError, match="No on-demand pricing data"):
        pricing.get_ondemand_usd_per_hour(
            instance_type="m6i.large",
            region="ap-southeast-2",
            os="Linux",
        )


def test_get_savingsplan_no_upfront_usd_per_hour_parses_rates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not hasattr(pricing, "get_savingsplan_no_upfront_usd_per_hour"):
        pytest.fail("pricing.get_savingsplan_no_upfront_usd_per_hour is not implemented")

    response = {
        "searchResults": [
            pricing_fixtures.make_savings_plan_result(
                usd_per_hour="0.052", duration_seconds=31_536_000
            ),
            pricing_fixtures.make_savings_plan_result(
                usd_per_hour="0.047", duration_seconds=94_608_000
            ),
        ]
    }
    client = DummySavingsPlansClient(response=response)

    def _fake_client(service_name: str, region_name: str | None = None) -> DummySavingsPlansClient:
        assert service_name == "savingsplans"
        return client

    _patch_boto3(monkeypatch, fake_client=_fake_client)

    result = pricing.get_savingsplan_no_upfront_usd_per_hour(
        instance_type="m6i.large",
        region="ap-southeast-2",
        os="Linux",
        plan_type="Compute",
        savingsPlanPaymentOptions="No Upfront",
    )

    assert result == {"1y": Decimal("0.052"), "3y": Decimal("0.047")}
    assert client.calls, "Expected aws_pricer.pricing to call describe_savings_plans_offering_rates"
    call_kwargs = client.calls[-1]

    assert call_kwargs.get("savingsPlanPaymentOptions") == ["No Upfront"]
    assert call_kwargs.get("savingsPlanTypes") == ["Compute"]
    filters: dict[str | None, tuple[str, ...]] = {}
    for entry in call_kwargs.get("filters", []):
        name = entry.get("name") or entry.get("Name")
        values = entry.get("values") or entry.get("Values") or []
        filters[name] = tuple(values)

    assert filters.get("instanceType") == ("m6i.large",)
    assert filters.get("region") == ("ap-southeast-2",)
    assert filters.get("productDescription") == ("Linux", "Linux/UNIX")
    assert filters.get("tenancy") == ("shared",)
    assert "planType" not in filters


@pytest.mark.parametrize(
    (
        "instance_type",
        "os",
        "product_description",
        "expected_three_year",
    ),
    (
        ("m5a.xlarge", "Linux", "Linux/UNIX", "0.307"),
        ("m5.large", "Linux", "Linux/UNIX", "0.16"),
        ("m6i.2xlarge", "Windows", "Windows", "0.25131"),
        ("m4.2xlarge", "Windows", "Windows", "0.2782"),
    ),
)
def test_get_savingsplan_no_upfront_usd_per_hour_prefers_box_usage_rates(
    monkeypatch: pytest.MonkeyPatch,
    instance_type: str,
    os: str,
    product_description: str,
    expected_three_year: str,
) -> None:
    if not hasattr(pricing, "get_savingsplan_no_upfront_usd_per_hour"):
        pytest.fail("pricing.get_savingsplan_no_upfront_usd_per_hour is not implemented")

    response = {
        "searchResults": [
            pricing_fixtures.make_savings_plan_result(
                usd_per_hour="0.35",
                duration_seconds=31_536_000,
                product_description=product_description,
                instance_type=instance_type,
                usage_type=f"APS2-BoxUsage:{instance_type}",
            ),
            pricing_fixtures.make_savings_plan_result(
                usd_per_hour=expected_three_year,
                duration_seconds=94_608_000,
                product_description=product_description,
                instance_type=instance_type,
                usage_type=f"APS2-BoxUsage:{instance_type}",
            ),
            pricing_fixtures.make_savings_plan_result(
                usd_per_hour="0.05",
                duration_seconds=94_608_000,
                product_description=product_description,
                instance_type=instance_type,
                usage_type=f"APS2-UnusedBox:{instance_type}",
            ),
        ]
    }
    client = DummySavingsPlansClient(response=response)

    def _fake_client(service_name: str, region_name: str | None = None) -> DummySavingsPlansClient:
        assert service_name == "savingsplans"
        return client

    _patch_boto3(monkeypatch, fake_client=_fake_client)

    result = pricing.get_savingsplan_no_upfront_usd_per_hour(
        instance_type=instance_type,
        region="ap-southeast-2",
        os=os,
        plan_type="Compute",
        savingsPlanPaymentOptions="No Upfront",
    )

    assert result == {
        "1y": Decimal("0.35"),
        "3y": Decimal(expected_three_year),
    }


def test_get_savingsplan_no_upfront_usd_per_hour_requires_one_and_three_year_rates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not hasattr(pricing, "get_savingsplan_no_upfront_usd_per_hour"):
        pytest.fail("pricing.get_savingsplan_no_upfront_usd_per_hour is not implemented")

    response = {
        "searchResults": [
            pricing_fixtures.make_savings_plan_result(
                usd_per_hour="0.052", duration_seconds=31_536_000
            )
        ]
    }
    client = DummySavingsPlansClient(response=response)

    def _fake_client(service_name: str, region_name: str | None = None) -> DummySavingsPlansClient:
        assert service_name == "savingsplans"
        return client

    _patch_boto3(monkeypatch, fake_client=_fake_client)

    with pytest.raises(ValueError, match="Savings Plans rates for both 1y and 3y are required"):
        pricing.get_savingsplan_no_upfront_usd_per_hour(
            instance_type="m6i.large",
            region="ap-southeast-2",
            os="Linux",
            plan_type="Compute",
            savingsPlanPaymentOptions="No Upfront",
        )
