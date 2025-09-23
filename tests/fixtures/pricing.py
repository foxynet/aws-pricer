"""Test fixtures for :mod:`aws_pricer.pricing` module.

Resources
---------
- Boto3 Pricing client documentation: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/pricing.html
  Sample query::

      import boto3

      pricing = boto3.client("pricing", region_name="us-east-1")
      response = pricing.get_products(
          ServiceCode="AmazonEC2",
          Filters=[
              {"Type": "TERM_MATCH", "Field": "instanceType", "Value": "m6i.large"},
              {"Type": "TERM_MATCH", "Field": "regionCode", "Value": "ap-southeast-2"},
              {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
              {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
              {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
              {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
          ],
          MaxResults=1,
      )

  Example response payload (abbreviated)::

      {
          "PriceList": [
              (
                  "{\"product\": {\"productFamily\": \"Compute Instance\"}, ...}"
              )
          ],
          "FormatVersion": "aws_v1"
      }

- Boto3 Savings Plans client documentation: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/savingsplans.html
  Sample query::

      savingsplans = boto3.client("savingsplans", region_name="us-east-1")
      response = savingsplans.describe_savings_plans_offering_rates(
          savingsPlanPaymentOptions=["No Upfront"],
          savingsPlanTypes=["Compute"],
          filters=[
              {"name": "instanceType", "values": ["m6i.large"]},
              {"name": "region", "values": ["ap-southeast-2"]},
              {"name": "productDescription", "values": ["Linux/UNIX"]},
          ],
      )

  Example response entry (abbreviated)::

      {
          "savingsPlanOffering": {
              "currency": "USD",
              "durationSeconds": 31536000,
              "planType": "Compute",
          },
          "properties": [
              {"name": "productDescription", "value": "Linux/UNIX"},
              {"name": "tenancy", "value": "shared"},
              {"name": "licenseModel", "value": "No License required"},
          ],
          "rate": "0.052",
          "unit": "Hrs",
      }
"""

from __future__ import annotations

import json
from typing import Any


def make_price_list_entry(*, usd_per_hour: str = "0.096", unit: str = "Hrs") -> str:
    """Return a minimal Pricing API price list entry as a JSON string."""
    return json.dumps(
        {
            "product": {
                "productFamily": "Compute Instance",
                "sku": "SAMPLE-SKU",
                "attributes": {
                    "instanceType": "m6i.large",
                    "regionCode": "ap-southeast-2",
                    "operatingSystem": "Linux",
                    "tenancy": "Shared",
                    "capacitystatus": "Used",
                    "preInstalledSw": "NA",
                },
            },
            "terms": {
                "OnDemand": {
                    "SAMPLE-SKU.Ondemand": {
                        "priceDimensions": {
                            "SAMPLE-SKU.DIMENSION": {
                                "unit": unit,
                                "pricePerUnit": {"USD": usd_per_hour},
                                "description": "Sample description",
                                "beginRange": "0",
                                "endRange": "Inf",
                            }
                        },
                        "sku": "SAMPLE-SKU",
                        "effectiveDate": "2024-01-01T00:00:00Z",
                        "offerTermCode": "JRTCKXETXF",
                    }
                }
            },
            "serviceCode": "AmazonEC2",
        }
    )


def make_savings_plan_result(
    *,
    usd_per_hour: str,
    duration_seconds: int,
    currency: str = "USD",
    unit: str = "Hrs",
    product_description: str = "Linux/UNIX",
    tenancy: str = "shared",
    license_model: str = "No License required",
) -> dict[str, Any]:
    """Return a minimal Savings Plans offering rate search result."""
    return {
        "savingsPlanOffering": {
            "offeringId": "sample-offering-id",
            "paymentOption": "No Upfront",
            "planType": "Compute",
            "durationSeconds": duration_seconds,
            "currency": currency,
        },
        "rate": usd_per_hour,
        "unit": unit,
        "productType": "EC2",
        "serviceCode": "AmazonEC2",
        "usageType": "APAC-Sydney-BoxUsage:m6i.large",
        "operation": "RunInstances",
        "properties": [
            {"name": "instanceFamily", "value": "m6i"},
            {"name": "productDescription", "value": product_description},
            {"name": "instanceType", "value": "m6i.large"},
            {"name": "tenancy", "value": tenancy},
            {"name": "licenseModel", "value": license_model},
            {"name": "region", "value": "ap-southeast-2"},
        ],
    }
