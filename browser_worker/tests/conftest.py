from __future__ import annotations

import os
import shutil

import pytest

from .site_server import Site

# CI installs Chromium with `playwright install --with-deps chromium`. In an environment with a pre-installed
# Chromium, point BROWSER_CHROMIUM_PATH at it.
if not os.environ.get("BROWSER_CHROMIUM_PATH") and os.path.exists("/opt/pw-browsers/chromium"):
    os.environ["BROWSER_CHROMIUM_PATH"] = "/opt/pw-browsers/chromium"


@pytest.fixture()
def site():
    with Site("onlinebooq") as s:
        yield s


@pytest.fixture()
def workdir(tmp_path):
    yield tmp_path
    shutil.rmtree(tmp_path, ignore_errors=True)
