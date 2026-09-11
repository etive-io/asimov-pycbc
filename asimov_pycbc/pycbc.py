"""PyCBC Inference Pipeline specification for Asimov."""

import glob
import importlib.resources
import os
import shutil

from asimov import config
from asimov.pipeline import Pipeline, PipelineException
from asimov.scheduler_utils import create_job_from_dict
from asimov.utils import set_directory


class PyCBC(Pipeline):
    """
    The PyCBC Inference Pipeline integration for Asimov.

    This class provides an interface between Asimov and ``pycbc_inference``,
    handling config templating, job submission via Asimov's scheduler
    abstraction, completion detection, and asset collection.

    Parameters
    ----------
    production : :class:`asimov.Production`
       The production object.
    category : str, optional
        The category of the job.
        Defaults to "analyses".
    """

    name = "PyCBC"
    STATUS = {"wait", "stuck", "stopped", "running", "finished"}

    def __init__(self, production, category=None):
        super(PyCBC, self).__init__(production, category)
        if not production.pipeline.lower() == "pycbc":
            raise PipelineException("Pipeline mismatch")

    @property
    def config_template(self):
        """
        The bundled Liquid template used to render a production's ``.ini``
        file when one doesn't already exist in the event repository.

        Asimov's generic ``manage build`` step calls ``production.make_config()``,
        which looks for this attribute on the pipeline (see
        ``Analysis.make_config`` in asimov core) before falling back to a
        template bundled inside asimov's own package -- which doesn't ship
        a PyCBC template.
        """
        return str(
            importlib.resources.files("asimov_pycbc").joinpath(
                "configs/pycbc.ini"
            )
        )

    def _output_file(self):
        """
        The path to the HDF5 samples file this production's
        ``pycbc_inference`` job writes and reads from on resume.
        """
        return os.path.join(self.production.rundir, f"{self.production.name}.hdf")

    def _executable(self):
        """
        Resolve the ``pycbc_inference`` executable.

        Resolved defensively rather than assuming
        ``config["pipelines"]["environment"]/bin/pycbc_inference`` exists
        (matching the approach used by the sibling asimov-bayeswave
        plugin): in minimal/containerised environments that config value
        may not point at the active environment. ``shutil.which`` also
        picks up an explicit per-production override via
        ``production.meta["executable"]``.
        """
        default_executable = os.path.join(
            config.get("pipelines", "environment"), "bin", "pycbc_inference"
        )
        executable = self.production.meta.get("executable", default_executable)
        executable = shutil.which(executable) or shutil.which("pycbc_inference")
        if executable is None:
            raise PipelineException(
                "Cannot find the pycbc_inference executable",
                production=self.production.name,
            )
        return executable

    def build_dag(self, dryrun=False):
        """
        Resolve the run directory and the location of the rendered ``.ini``
        file for this production.

        ``pycbc_inference`` has no separate DAG-building step of its own --
        it is submitted directly as a single job (see ``submit_dag``) --
        but asimov's generic ``manage build submit`` CLI unconditionally
        calls ``build_dag`` on every pipeline before ``submit_dag``, so
        this must exist.
        """
        if self.production.rundir:
            self.production.rundir = os.path.abspath(self.production.rundir)
        else:
            self.production.rundir = os.path.join(
                config.get("general", "rundir_default"),
                self.production.event.name,
                self.production.name,
            )
        os.makedirs(self.production.rundir, exist_ok=True)

        if self.production.event.repository:
            configs = self.production.event.repository.find_prods(
                self.production.name, self.category
            )
            if not configs:
                raise PipelineException(
                    f"No configuration file found for {self.production.name} "
                    f"in the event repository's '{self.category}' directory.",
                    production=self.production.name,
                )
            ini = os.path.join(
                self.production.event.repository.directory, self.category, configs[0]
            )
        else:
            ini = f"{self.production.name}.ini"

        if dryrun:
            print(f"Configuration file: {ini}")

        return ini

    def submit_dag(self, dryrun=False):
        """
        Submit a ``pycbc_inference`` job to the scheduler.

        Uses Asimov's scheduler abstraction (``self.scheduler``, HTCondor
        or Slurm) rather than hand-rolling ``htcondor``/``htcondor2`` calls
        directly.

        Parameters
        ----------
        dryrun : bool, optional
           If True then the job will not be submitted, but the command and
           submit description will be printed to stdout.

        Returns
        -------
        int
           The cluster ID assigned to the submitted job.

        Raises
        ------
        PipelineException
           This will be raised if the pipeline fails to submit the job.
        """
        ini = self.build_dag(dryrun=dryrun)
        rundir = self.production.rundir
        output_file = self._output_file()

        # Resume from a checkpoint left by a previous (e.g. pre-empted or
        # evicted) attempt when one exists, rather than clobbering it --
        # pycbc_inference checkpoints its own progress to
        # `<output-file>.checkpoint` and resumes automatically as long as
        # `--force` isn't passed.
        resume = os.path.exists(f"{output_file}.checkpoint") or os.path.exists(
            output_file
        )

        nprocesses = self.production.meta.get("scheduler", {}).get("processes", 1)

        command = [
            self._executable(),
            "--config-files",
            ini,
            "--output-file",
            output_file,
            "--nprocesses",
            str(nprocesses),
        ]
        if not resume:
            command += ["--force"]

        batch_name = f"PyCBC/{self.production.event.name}/{self.production.name}"

        self.logger.info(" ".join(command))

        with open(os.path.join(rundir, "pycbc.sh"), "w") as script_file:
            script_file.write(" ".join(command) + "\n")

        submit_description = {
            "executable": command[0],
            "arguments": " ".join(command[1:]),
            "output": os.path.join(rundir, f"{self.production.name}.out"),
            "error": os.path.join(rundir, f"{self.production.name}.err"),
            "log": os.path.join(rundir, f"{self.production.name}.log"),
            "request_cpus": str(nprocesses),
            "request_memory": str(
                self.production.meta.get("scheduler", {}).get("request memory", "4096MB")
            ),
            "request_disk": str(
                self.production.meta.get("scheduler", {}).get("request disk", "4096MB")
            ),
            "environment": "HDF5_USE_FILE_LOCKING=FALSE OMP_NUM_THREADS=1",
            "getenv": "true",
            "batch_name": batch_name,
        }

        accounting_group = self.production.meta.get("scheduler", {}).get(
            "accounting group"
        )
        if accounting_group:
            submit_description["accounting_group_user"] = config.get(
                "condor", "user"
            )
            submit_description["accounting_group"] = accounting_group

        if dryrun:
            print(f"Would submit: {' '.join(command)}")
            print("SUBMIT DESCRIPTION")
            print("-------------------")
            print(submit_description)
            return None

        with set_directory(rundir):
            try:
                job = create_job_from_dict(submit_description)
                cluster_id = self.scheduler.submit(job)
            except (FileNotFoundError, RuntimeError) as error:
                raise PipelineException(
                    f"The pycbc_inference job could not be submitted: {error}",
                    production=self.production.name,
                ) from error

        self.production.status = "running"
        self.production.job_id = int(cluster_id)
        self.logger.info(f"Submitted PyCBC job: {self.production.job_id}")
        return int(cluster_id)

    def detect_completion(self):
        """
        Check for the production of a posterior samples HDF5 file to
        signal that the job has completed.
        """
        output_file = self._output_file()
        if not os.path.exists(output_file):
            return False
        try:
            import h5py

            with h5py.File(output_file, "r") as f:
                return len(f.keys()) > 0
        except ImportError:
            return True
        except OSError:
            # The file may still be mid-write (e.g. a checkpoint being
            # promoted to the final output).
            return False

    def samples(self):
        """
        Collect the combined samples file for PESummary.
        """
        output_file = self._output_file()
        return [output_file] if os.path.exists(output_file) else []

    def collect_assets(self):
        """
        Gather the results assets for this job, so that a downstream
        production (for example a PESummary post-processing production
        wired up via ``needs:``) can pick them up through
        ``production._previous_assets()``.
        """
        assets = {"samples": self.samples()}
        if self.production.event.repository:
            configs = self.production.event.repository.find_prods(
                self.production.name, self.category
            )
            if configs:
                assets["config"] = configs[0]
        return assets

    def collect_logs(self):
        """
        Collect all of the log files which have been produced by this
        production and return their contents as a dictionary.
        """
        logs = (
            glob.glob(f"{self.production.rundir}/*.err")
            + glob.glob(f"{self.production.rundir}/*.out")
            + glob.glob(f"{self.production.rundir}/*.log")
        )
        messages = {}
        for log in logs:
            with open(log, "r") as log_f:
                messages[os.path.basename(log)] = log_f.read()
        return messages

    def after_completion(self):
        """
        Mark this production as finished once its job has completed.

        This deliberately does *not* reach out and submit a PESummary (or
        any other) post-processing job itself. Post-processing is instead
        expressed as its own, separate production with a ``needs:``
        dependency on this one (see e.g.
        `asimov-pesummary <https://github.com/etive-io/asimov-pesummary>`_):
        Asimov's own dependency resolution builds and submits that
        production once this one reaches ``finished``, and it picks up
        this production's samples via ``collect_assets()`` through
        ``production._previous_assets()``. This matches the pattern used
        by other post-completion-only pipelines (e.g. the ``FakeCBCPipeline``
        test pipeline in asimov-pesummary itself), and avoids this plugin
        needing any knowledge of what -- if anything -- consumes its
        output.
        """
        super().after_completion()

    def resurrect(self):
        """
        Attempt to resurrect a failed or evicted job by resubmitting it.

        ``pycbc_inference`` checkpoints its own progress, so resubmitting
        the same job (without ``--force``, handled automatically by
        ``submit_dag``) resumes from where it left off.
        """
        try:
            count = self.production.meta["resurrections"]
        except KeyError:
            count = 0
        checkpoint = f"{self._output_file()}.checkpoint"
        if count < 5 and os.path.exists(checkpoint):
            count += 1
            self.production.meta["resurrections"] = count
            self.submit_dag()
