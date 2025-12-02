import unittest

from asimov.event import Event
from asimov.analysis import SimpleAnalysis
from asimov.pipeline import Pipeline
from asimov_pycbc import PyCBC
import os

class TestPyCBCIntegration(unittest.TestCase):

    def test_make_config(self):
        """Check that asimov can make a config file for pycbc."""

        subject = Event(name="GW150914")
        analysis = SimpleAnalysis(subject=subject,
                                  name="Test 1",
                                  pipeline="pycbc",
                                  interferometers=["L1", "H1"]
        )
        cfg_path = "test.ini"
        analysis.make_config(cfg_path)
        self.assertTrue(os.path.exists(cfg_path))
        # Parse config to ensure it is a valid INI
        parser = Pipeline.read_ini(cfg_path)
        self.assertTrue(parser.has_section("data"))
        os.remove(cfg_path)

    def test_submit_description(self):
        """Ensure submit description can be built and job submission invoked."""
        subject = Event(name="GW150914")
        analysis = SimpleAnalysis(subject=subject,
                                  name="TestSubmit",
                                  pipeline="pycbc",
                                  interferometers=["L1", "H1"],
                                  sampler={"processes": 1},
                                  rundir="."
        )

        # Build command and ensure contains pycbc_inference and ini
        cmd = analysis.pipeline.build_dag()
        self.assertIn("pycbc_inference", cmd[0])
        self.assertTrue(cmd[1].endswith(".ini"))

    def test_completion_and_samples(self):
        subject = Event(name="GW150914")
        analysis = SimpleAnalysis(subject=subject,
                                  name="TestComplete",
                                  pipeline="pycbc",
                                  interferometers=["L1", "H1"],
                                  rundir="."
        )
        # Create dummy output to simulate completion
        out_file = os.path.join(".", "posterior_samples.h5")
        with open(out_file, "w") as fh:
            fh.write("dummy")
        self.assertTrue(analysis.pipeline.detect_completion())
        samples = analysis.pipeline.samples()
        self.assertTrue(any(p.endswith("posterior_samples.h5") for p in samples))
        os.remove(out_file)

    def test_ini_validation(self):
        subject = Event(name="GW150914")
        analysis = SimpleAnalysis(subject=subject,
                                  name="Validate",
                                  pipeline="pycbc",
                                  interferometers=["L1", "H1"]
        )
        cfg_path = "Validate.ini"
        analysis.make_config(cfg_path)
        parser = analysis.pipeline.read_ini()
        # If validation passes, sections exist
        for s in ["data","sampler","model","variable_params","static_params"]:
            self.assertTrue(parser.has_section(s))
        os.remove(cfg_path)
