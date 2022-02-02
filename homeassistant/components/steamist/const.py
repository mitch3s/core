"""Constants for the Steamist integration."""

import asyncio

import aiohttp

DOMAIN = "steamist"

CONNECTION_EXCEPTIONS = (asyncio.TimeoutError, aiohttp.ClientError)

CONF_MODEL = "model"

STARTUP_SCAN_TIMEOUT = 5
DISCOVER_SCAN_TIMEOUT = 10

DISCOVERY = "discovery"
