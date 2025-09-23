# aws-pricer
aws-pricer is a small Python library that fetches on‑demand and Savings Plans hourly rates for AWS Compute, via boto3.

---

## Overview

`aws-pricer` is a small Python library that fetches **on‑demand** and **Savings Plans** hourly rates for AWS Compute.

* On‑Demand prices via the **AWS Price List Query API** (`boto3.client("pricing")`).
* Savings Plan rates via **Savings Plans Offering Rates** (`boto3.client("savingsplans")`).
* Clean, typed Python interface; PEP 8/Flake/Black compatible; tested with pytest.
* Optional **Invoke** (`invoke`) tasks for developer ergonomics.

> ⚠️ You need AWS credentials with permissions for **Pricing** and **SavingsPlans** APIs. Pricing endpoint is in `us-east-1`; filter results by `regionCode` for your target region.

## Why this project?

* Provide a **single entry‑point** to compare AWS Compute on‑demand vs SP No‑Upfront (1y / 3y).
* Return **normalized** numbers (USD/hr) and a simple summary to compute % savings.
* Be a **good citizen** in Python packaging: pip‑installable, typed, tested, linted.

## Features (MVP)

* `get_ondemand_usd_per_hour(instance_type, region, os)`
* `get_savingsplan_usd_per_hour(instance_type, region, os, plan_type, savingsPlanPaymentOptions)` → `{"1y": Decimal, "3y": Decimal}`
* CLI entrypoint: `aws-pricer price --instance-type m6i.large --region ap-southeast-2 --os Linux --plan-type compute --payment-option noupfront`

## Roadmap (stretch)

* Batch queries & CSV/JSON output

## Installation

```bash
# Recommended
python -m venv .venv && source .venv/bin/activate  # (Windows: .venv\Scripts\activate)

pip install --upgrade pip
pip install aws-pricer  # (when published)

# From source
pip install -e .[dev]
```

**Dev extras** include: `boto3`, `pytest`, `pytest-cov`, `mypy`, `ruff`, `invoke`.

## Quick start

```python
from aws_pricer import pricing

od = pricing.get_ondemand_usd_per_hour("m6i.large", "ap-southeast-2", os="Linux")
sp = pricing.get_savingsplan_no_upfront_usd_per_hour("m6i.large", "ap-southeast-2", os="Linux", plan_type="Compute", savingsPlanPaymentOptions="No Upfront")
print("On-Demand:", od)
print("SP No Upfront:", sp)  # {"1y": Decimal("…"), "3y": Decimal("…")}
```

**CLI (planned):**

```bash
aws-pricer price --instance-type m6i.large --region ap-southeast-2 --os Linux
```

## Credentials & permissions

Set AWS creds via environment (`AWS_PROFILE`, `AWS_ACCESS_KEY_ID`, etc.) or SSO. Minimal IAM actions:

* `pricing:GetProducts`
* `savingsplans:DescribeSavingsPlansOfferingRates`

> Pricing API endpoint is **us-east-1**; keep your `boto3.client("pricing", region_name="us-east-1")` and filter by `regionCode`.

## Project layout

```
aws-pricer/
├─ src/
│  └─ aws_pricer/
│     ├─ __init__.py
│     ├─ pricing.py          # core functions
│     ├─ cli.py              # optional click/typer-based CLI
│     └─ types.py            # dataclasses / TypedDicts
├─ tests/
│  ├─ test_pricing.py
│  └─ fixtures/
├─ tasks.py                  # invoke tasks (lint, format, test, build, price)
├─ pyproject.toml            # build-system (PEP 517/518), tool configs
├─ README.md
├─ AGENTS.md                 # guides to drive Codex/Copilot agents
├─ LICENSE
└─ CHANGELOG.md
```

## Tooling & quality

* **PEP 8 + Imports**: `ruff` (includes many flake8 rules)
* **Formatting**: `ruff`
* **Typing**: `mypy`
* **Tests**: `pytest`, `pytest-cov`
* **Tasks**: `invoke` (see `tasks.py`)

## Invoke tasks (baseline)

Add a `tasks.py` with targets like:

```python
from invoke import task

@task
def format(c):
    c.run("black src tests")

@task
def lint(c):
    c.run("ruff check src tests")

@task
def typecheck(c):
    c.run("mypy src")

@task
def test(c):
    c.run("pytest -q --cov=aws_pricer --cov-report=term-missing")

@task
def build(c):
    c.run("python -m build")

@task
def price(c, instance_type, region, os="Linux", plan_type="Compute", payment_option="No Upfront"):
    """Ad-hoc pricing via library functions"""
    import json
    from aws_pricer import pricing as p
    od = p.get_ondemand_usd_per_hour(instance_type, region, os=os)
    sp = p.get_savingsplan_no_upfront_usd_per_hour(instance_type, region, os=os, plan_type=plan_type, savingsPlanPaymentOptions=payment_option)
    print(json.dumps({"on_demand": str(od), "savings_plan": {k: str(v) for k,v in sp.items()}}, indent=2))
```

Usage:

```bash
invoke format
invoke lint
invoke test
invoke price --instance-type m6i.large --region ap-southeast-2 --os Linux --payment-option "No Upfront"
```

## Testing strategy

* **Unit tests** for:

  * correct filter construction for `get_products`
  * parsing of `terms.OnDemand.priceDimensions`
  * mapping `durationSeconds` → `1y/3y` for SP
* **Integration tests** (optional, behind marker) that hit live AWS with `-m live`
* Use `botocore.stub.Stubber` or `moto` (if/when SP support is adequate) for predictable stubs.

Example test layout:

```bash
pytest -q
pytest -q -m live  # runs tests requiring real AWS creds
```

## Release & packaging

* Managed via **`pyproject.toml`** (PEP 517/518), build with `build`.
* Versioning: SemVer; maintain `CHANGELOG.md`.
* Publish: `twine upload dist/*` (via `invoke release` task, optional).

## Security & limits

* Don’t log credentials. Avoid printing raw API responses in production.
* Handle pagination for SP offering rates.
* Cache throttling/backoffs if batching queries.


PRs welcome. Run `invoke format lint typecheck test` before submitting.

