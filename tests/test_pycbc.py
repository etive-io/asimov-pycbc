"""Tests for the PyCBC pipeline integration."""

import os
from unittest.mock import Mock, patch

import pytest
from asimov.pipeline import PipelineException

from asimov_pycbc import PyCBC


class TestPyCBCInit:
    """Test PyCBC initialization."""

    def test_init_success(self, mock_production, mock_config):
        pipeline = PyCBC(mock_production)
        assert pipeline.name == "PyCBC"
        assert pipeline.production == mock_production
        assert "wait" in pipeline.STATUS

    def test_init_wrong_pipeline(self, mock_production, mock_config):
        mock_production.pipeline = "bilby"
        with pytest.raises(PipelineException, match="Pipeline mismatch"):
            PyCBC(mock_production)

    def test_init_sets_up_logger(self, mock_production, mock_config):
        """Regression test: the previous implementation overrode
        Pipeline.__init__ without calling super(), so self.logger was never
        set and any method that logged (almost all of them) raised
        AttributeError."""
        pipeline = PyCBC(mock_production)
        assert pipeline.logger is not None


class TestConfigTemplate:
    """Test the config_template property used by asimov's `manage build`
    to render an ini when one doesn't already exist in the event
    repository."""

    def test_config_template_is_a_real_bundled_file(self, mock_production, mock_config):
        pipeline = PyCBC(mock_production)
        assert os.path.exists(pipeline.config_template)

    def test_config_template_is_named_pycbc_ini(self, mock_production, mock_config):
        pipeline = PyCBC(mock_production)
        assert os.path.basename(pipeline.config_template) == "pycbc.ini"


class TestBuildDag:
    """Test resolution of rundir and config file location."""

    def test_build_dag_resolves_rundir(self, mock_production, mock_config, temp_dir):
        mock_production.rundir = os.path.join(temp_dir, "run")
        pipeline = PyCBC(mock_production)
        ini = pipeline.build_dag()
        assert os.path.isdir(mock_production.rundir)
        assert ini.endswith("TestProduction.ini")

    def test_build_dag_falls_back_to_rundir_default(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = None
        mock_config.get = lambda section, key: (
            temp_dir if (section, key) == ("general", "rundir_default") else ""
        )
        pipeline = PyCBC(mock_production)
        pipeline.build_dag()
        assert mock_production.rundir == os.path.join(
            temp_dir, mock_production.event.name, mock_production.name
        )

    def test_build_dag_dryrun_does_not_raise(self, mock_production, mock_config, temp_dir):
        mock_production.rundir = os.path.join(temp_dir, "run")
        pipeline = PyCBC(mock_production)
        pipeline.build_dag(dryrun=True)  # must not raise


class TestSubmitDag:
    """Test job submission via Asimov's scheduler abstraction."""

    # submit_dag() uses self.scheduler.submit(...) (the asimov>=0.7
    # scheduler abstraction, via asimov.scheduler_utils.create_job_from_dict)
    # rather than hand-rolling htcondor/htcondor2 schedd calls directly, as
    # the original implementation did.

    def test_submit_dag_uses_scheduler_abstraction(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = os.path.join(temp_dir, "run")

        with patch("asimov_pycbc.pycbc.shutil.which", return_value="/opt/conda/bin/pycbc_inference"):
            pipeline = PyCBC(mock_production)
            pipeline._scheduler = Mock()
            pipeline._scheduler.submit.return_value = 12345

            cluster_id = pipeline.submit_dag(dryrun=False)

        assert cluster_id == 12345
        assert mock_production.job_id == 12345
        assert mock_production.status == "running"
        assert pipeline._scheduler.submit.called

    def test_submit_dag_first_submission_uses_force(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = os.path.join(temp_dir, "run")
        with patch("asimov_pycbc.pycbc.shutil.which", return_value="/opt/conda/bin/pycbc_inference"):
            pipeline = PyCBC(mock_production)
            pipeline._scheduler = Mock()
            pipeline._scheduler.submit.return_value = 1

            pipeline.submit_dag(dryrun=False)

        job = pipeline._scheduler.submit.call_args[0][0]
        assert "--force" in job.kwargs["arguments"]

    def test_submit_dag_resumes_without_force_when_checkpoint_exists(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = os.path.join(temp_dir, "run")
        os.makedirs(mock_production.rundir, exist_ok=True)
        checkpoint = os.path.join(mock_production.rundir, "TestProduction.hdf.checkpoint")
        with open(checkpoint, "w") as f:
            f.write("x")

        with patch("asimov_pycbc.pycbc.shutil.which", return_value="/opt/conda/bin/pycbc_inference"):
            pipeline = PyCBC(mock_production)
            pipeline._scheduler = Mock()
            pipeline._scheduler.submit.return_value = 1

            pipeline.submit_dag(dryrun=False)

        job = pipeline._scheduler.submit.call_args[0][0]
        assert "--force" not in job.kwargs["arguments"]

    def test_submit_dag_dryrun_does_not_call_scheduler(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = os.path.join(temp_dir, "run")
        with patch("asimov_pycbc.pycbc.shutil.which", return_value="/opt/conda/bin/pycbc_inference"):
            pipeline = PyCBC(mock_production)
            pipeline._scheduler = Mock()

            result = pipeline.submit_dag(dryrun=True)

        assert result is None
        pipeline._scheduler.submit.assert_not_called()

    def test_submit_dag_missing_executable_raises_clear_exception(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = os.path.join(temp_dir, "run")
        with patch("asimov_pycbc.pycbc.shutil.which", return_value=None):
            pipeline = PyCBC(mock_production)
            with pytest.raises(PipelineException, match="pycbc_inference"):
                pipeline.submit_dag(dryrun=False)

    def test_submit_dag_scheduler_failure(self, mock_production, mock_config, temp_dir):
        mock_production.rundir = os.path.join(temp_dir, "run")
        with patch("asimov_pycbc.pycbc.shutil.which", return_value="/opt/conda/bin/pycbc_inference"):
            pipeline = PyCBC(mock_production)
            pipeline._scheduler = Mock()
            pipeline._scheduler.submit.side_effect = RuntimeError("could not submit")

            with pytest.raises(PipelineException, match="could not be submitted"):
                pipeline.submit_dag(dryrun=False)

    def test_submit_dag_sets_accounting_group(self, mock_production, mock_config, temp_dir):
        mock_production.rundir = os.path.join(temp_dir, "run")
        with patch("asimov_pycbc.pycbc.shutil.which", return_value="/opt/conda/bin/pycbc_inference"):
            pipeline = PyCBC(mock_production)
            pipeline._scheduler = Mock()
            pipeline._scheduler.submit.return_value = 1

            pipeline.submit_dag(dryrun=False)

        job = pipeline._scheduler.submit.call_args[0][0]
        assert job.kwargs["accounting_group"] == "ligo.dev.o4.cbc.pe.pycbc"


class TestDetectCompletion:
    """Test completion detection."""

    def test_detect_completion_no_output_file(self, mock_production, mock_config, temp_dir):
        mock_production.rundir = temp_dir
        pipeline = PyCBC(mock_production)
        assert pipeline.detect_completion() is False

    def test_detect_completion_output_file_exists_no_h5py(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = temp_dir
        output = os.path.join(temp_dir, "TestProduction.hdf")
        with open(output, "w") as f:
            f.write("not really hdf5")

        pipeline = PyCBC(mock_production)
        with patch.dict("sys.modules", {"h5py": None}):
            # Simulate h5py being unimportable; detect_completion should
            # fall back to a plain existence check rather than crashing.
            assert pipeline.detect_completion() in (True, False)


class TestSamplesAndAssets:
    def test_samples_empty_when_no_output(self, mock_production, mock_config, temp_dir):
        mock_production.rundir = temp_dir
        pipeline = PyCBC(mock_production)
        assert pipeline.samples() == []

    def test_samples_returns_output_file(self, mock_production, mock_config, temp_dir):
        mock_production.rundir = temp_dir
        output = os.path.join(temp_dir, "TestProduction.hdf")
        with open(output, "w") as f:
            f.write("x")
        pipeline = PyCBC(mock_production)
        assert pipeline.samples() == [output]

    def test_collect_assets_includes_config(self, mock_production, mock_config, temp_dir):
        mock_production.rundir = temp_dir
        pipeline = PyCBC(mock_production)
        assets = pipeline.collect_assets()
        assert assets["config"] == "TestProduction.ini"
        assert assets["samples"] == []


class TestAfterCompletion:
    """Test completion behaviour.

    ``after_completion()`` deliberately does *not* know anything about
    PESummary or any other post-processing plugin. Post-processing is
    expressed as a separate production with a ``needs:`` dependency on this
    one (see asimov-pesummary), resolved entirely by Asimov's own dependency
    machinery -- not by this pipeline reaching out and submitting a job for
    it directly.
    """

    def test_after_completion_marks_production_finished(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = temp_dir
        mock_production.status = "running"
        pipeline = PyCBC(mock_production)

        pipeline.after_completion()

        assert mock_production.status == "finished"

    def test_module_does_not_import_entry_points(self):
        """Regression test: the module must not import importlib.metadata's
        entry_points at all any more -- a previous version of after_completion()
        looked up the ``pesummary`` pipeline via the ``asimov.pipelines``
        entry-point group and submitted a job for it directly. Asserting the
        import itself is gone is a direct check; asserting no particular
        exception was raised (the previous version of this test) would
        trivially pass even if entry_points() were still called."""
        import asimov_pycbc.pycbc as pycbc_module

        assert not hasattr(pycbc_module, "entry_points")

    def test_after_completion_does_not_set_job_id(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = temp_dir
        pipeline = PyCBC(mock_production)

        pipeline.after_completion()

        assert "job id" not in mock_production.meta


class TestResurrect:
    def test_resurrect_resubmits_when_checkpoint_exists(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = temp_dir
        mock_production.meta.pop("resurrections", None)
        checkpoint = os.path.join(temp_dir, "TestProduction.hdf.checkpoint")
        with open(checkpoint, "w") as f:
            f.write("x")

        pipeline = PyCBC(mock_production)
        with patch.object(pipeline, "submit_dag") as mock_submit:
            pipeline.resurrect()

        mock_submit.assert_called_once()
        assert mock_production.meta["resurrections"] == 1

    def test_resurrect_no_checkpoint_does_not_resubmit(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = temp_dir
        pipeline = PyCBC(mock_production)
        with patch.object(pipeline, "submit_dag") as mock_submit:
            pipeline.resurrect()

        mock_submit.assert_not_called()

    def test_resurrect_stops_after_five_attempts(
        self, mock_production, mock_config, temp_dir
    ):
        mock_production.rundir = temp_dir
        mock_production.meta["resurrections"] = 5
        checkpoint = os.path.join(temp_dir, "TestProduction.hdf.checkpoint")
        with open(checkpoint, "w") as f:
            f.write("x")

        pipeline = PyCBC(mock_production)
        with patch.object(pipeline, "submit_dag") as mock_submit:
            pipeline.resurrect()

        mock_submit.assert_not_called()


class TestRealConfigRendering:
    """Exercise the real Liquid rendering path (asimov's own
    ``Analysis.make_config()``), rather than just checking that the
    template file exists -- this is what actually catches undefined-
    variable/syntax bugs in the bundled ini template."""

    def test_template_renders_a_valid_ini(
        self, mock_production, mock_config, temp_dir
    ):
        from asimov import config as real_config
        from asimov.pipeline import Pipeline
        from liquid import Liquid

        pipeline = PyCBC(mock_production)

        liq = Liquid(pipeline.config_template)
        rendered = liq.render(
            production=mock_production,
            analysis=mock_production,
            pipeline=pipeline,
            config=real_config,
        )

        cfg_path = os.path.join(temp_dir, "pycbc-test.ini")
        with open(cfg_path, "w") as f:
            f.write(rendered)

        parser = Pipeline.read_ini(cfg_path)
        for section in ("data", "model", "sampler", "variable_params", "static_params"):
            assert parser.has_section(section), f"Missing section: {section}"
        assert (
            parser.get("static_params", "approximant")
            == mock_production.meta["waveform"]["approximant"]
        )
        assert parser.get("data", "trigger-time") == str(
            mock_production.meta["event time"]
        )


def test_module_imports():
    from asimov_pycbc import PyCBC, __version__

    assert PyCBC is not None
    assert __version__ is not None
