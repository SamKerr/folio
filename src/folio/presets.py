"""Capture presets and choice lists shared by the GUIs."""

from __future__ import annotations

CAPTURE_PRESETS: dict[str, dict[str, int]] = {
    "Fast": {
        "image_wait_ms": 2_000,
        "asset_quiet_ms": 500,
        "page_asset_timeout_ms": 30_000,
        "settle_ms": 500,
        "timeout_secs": 45,
    },
    "Balanced": {
        "image_wait_ms": 5_000,
        "asset_quiet_ms": 750,
        "page_asset_timeout_ms": 60_000,
        "settle_ms": 1_000,
        "timeout_secs": 60,
    },
    "Thorough": {
        "image_wait_ms": 15_000,
        "asset_quiet_ms": 1_500,
        "page_asset_timeout_ms": 120_000,
        "settle_ms": 2_000,
        "timeout_secs": 90,
    },
}

PAGE_CONCURRENCY_CHOICES = ("4", "8", "12", "20", "32")
ASSET_CONCURRENCY_CHOICES = ("4", "8", "12", "20", "32")
IMAGE_WAIT_CHOICES = ("0", "2000", "5000", "10000", "15000", "30000")
ASSET_QUIET_CHOICES = ("0", "500", "750", "1000", "1500", "3000")
PAGE_ASSET_CAP_CHOICES = ("30000", "60000", "90000", "120000")
SETTLE_CHOICES = ("0", "500", "1000", "2000", "5000")
TIMEOUT_CHOICES = ("30", "45", "60", "90", "120")
