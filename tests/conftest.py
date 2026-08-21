"""Pytest configuration and fixtures."""

import tempfile
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_production():
    """Create a mock production object for testing."""
    production = MagicMock()
    production.name = "TestProduction"
    production.pipeline = "pycbc"
    production.category = "analyses"
    production.rundir = "/tmp/test_rundir"
    production.status = "wait"
    production.job_id = None

    production.event = MagicMock()
    production.event.name = "GW150914"
    production.event.repository = MagicMock()
    production.event.repository.directory = "/tmp/test_repo"
    production.event.repository.find_prods.return_value = ["TestProduction.ini"]

    production.meta = {
        "event time": 1126259462.4,
        "interferometers": ["H1", "L1"],
        "waveform": {
            "approximant": "IMRPhenomPv2",
            "reference frequency": 20,
        },
        "likelihood": {
            "sample rate": 2048,
            "segment start": -6,
            "post trigger time": 2,
            "minimum frequency": {"H1": 20, "L1": 20},
        },
        "data": {
            "channels": {
                "H1": "H1:GDS-CALIB_STRAIN",
                "L1": "L1:GDS-CALIB_STRAIN",
            },
            "frame types": {
                "H1": "H1_HOFT_C00",
                "L1": "L1_HOFT_C00",
            },
        },
        "sampler": {
            "sampler": "dynesty",
            "sampler kwargs": {"nlive": 2000, "dlogz": 0.1},
        },
        "scheduler": {
            "accounting group": "ligo.dev.o4.cbc.pe.pycbc",
            "processes": 2,
        },
    }

    production.get_meta = lambda key: production.meta.get(key)

    return production


@pytest.fixture
def mock_config(monkeypatch):
    """Mock the asimov config object."""
    config_values = {
        ("general", "rundir_default"): "/tmp/run",
        ("general", "webroot"): "/tmp/web",
        ("pipelines", "environment"): "/opt/conda",
        ("condor", "user"): "test.user",
    }

    def mock_get(section, key):
        return config_values.get((section, key), "")

    mock_config_module = MagicMock()
    mock_config_module.get = mock_get

    monkeypatch.setattr("asimov_pycbc.pycbc.config", mock_config_module)
    return mock_config_module


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir
