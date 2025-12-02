"""
Asimov integration for running PyCBC Inference.
"""

import os
from importlib import resources
import warnings
try:
    from asimov import config as asimov_config
except Exception:
    asimov_config = None

from asimov.pipeline import Pipeline

__version__ = "0.1.0"


class PyCBC(Pipeline):
    """
    PyCBC Inference pipeline for Asimov.

    Provides config templating and scaffolding for submitting
    a `pycbc_inference` job to an HTCondor scheduler.
    """

    # Path to the Liquid template used by Analysis.make_config
    try:
        _template_path = resources.files(__name__).joinpath("pycbc-inference.ini")
        config_template = str(_template_path)
    except Exception:
        # Fallback: relative path within the package
        config_template = os.path.join(os.path.dirname(__file__), "pycbc-inference.ini")
    _pipeline_command = "pycbc_inference"
    name = "pycbc"

    def __init__(self, production):
        # Asimov's Pipeline expects a Production/Analysis instance
        super().__init__(production)

    @property
    def previous_assets(self):
        """Expose previous job assets for Liquid templating."""
        try:
            return self.production._previous_assets()
        except Exception:
            return {}

    @property
    def channel_names(self):
        """Return PyCBC channel-name string from production.meta.

        Supports either a single string at meta['data']['channel name'] or
        a mapping at meta['data']['channel names'] with keys of IFO codes.
        """
        data = self.production.meta.get("data", {})
        # Single string
        if isinstance(data.get("channel name"), str) and data.get("channel name").strip():
            return data.get("channel name")
        # Dict mapping: {"H1": "H1:STRAIN", "L1": "L1:STRAIN"}
        chan_map = data.get("channel names") or data.get("channels")
        if isinstance(chan_map, dict) and chan_map:
            parts = []
            for ifo, name in chan_map.items():
                # If value already includes IFO prefix, keep as-is
                if ":" in name:
                    parts.append(name)
                else:
                    parts.append(f"{ifo}:{name}")
            return " ".join(parts)
        return ""

    @property
    def frame_files(self):
        """Return PyCBC frame-files string.

        Accepts either a single string in `production.meta['data']['frame files']`
        or a dict mapping of IFO->path in `production.meta['data']['frame files']`.
        Falls back to previous assets key 'frame-files'.
        """
        data = self.production.meta.get("data", {})
        ff = data.get("frame files") or data.get("frame-files")
        if isinstance(ff, str) and ff.strip():
            return ff
        if isinstance(ff, dict) and ff:
            parts = []
            for ifo, path in ff.items():
                # Normalize to IFO:path
                if ":" in path:
                    parts.append(path)
                else:
                    parts.append(f"{ifo}:{path}")
            return " ".join(parts)
        # Fallback to previous assets
        prev = self.previous_assets.get("frame-files")
        if isinstance(prev, dict):
            parts = []
            for ifo, path in prev.items():
                parts.append(f"{ifo}:{path}")
            return " ".join(parts)
        return prev or ""

    def detect_completion(self):
        """
        Check for the production of a final posterior file to
        signal that a job has been completed.
        """
        # Placeholder: detect common PyCBC inference outputs
        rundir = getattr(self.production, "rundir", None)
        if not rundir:
            return False
        candidates = [
            os.path.join(rundir, "posterior_samples.h5"),
            os.path.join(rundir, "inference.hdf"),
        ]
        return any(os.path.exists(p) for p in candidates)

    def build_dag(self):
        """
        Construct the command used to run ``pycbc_inference``.
        """
        # Build a basic command from the production context.
        ini = os.path.join(self.production.rundir or ".", f"{self.production.name}.ini")
        nproc = (
            self.production.meta.get("sampler", {}).get("processes")
            or self.production.meta.get("sampler", {}).get("nprocesses")
            or 1
        )

        command = [
            self._pipeline_command,
            ini,
            "--nprocesses",
            str(nproc),
            "--force",
        ]
        self.logger.info(" ".join(command))
        return command
        

    def submit_dag(self):
        """
        Submit the DAG file to the cluster.
        """
        # Prefer HTCondor submission similar to PESummary pipeline
        try:
            warnings.filterwarnings("ignore", module="htcondor2")
            import htcondor2 as htcondor  # NoQA
        except ImportError:
            warnings.filterwarnings("ignore", module="htcondor")
            import htcondor  # NoQA

        command = self.build_dag()

        rundir = getattr(self.production, "rundir", os.getcwd())
        out_base = os.path.join(rundir, self.production.name)

        # Build submit description
        # Expected outputs to transfer back to the submit node
        transfer_files = [
            f"{self.production.name}.ini",
            "posterior_samples.h5",
            "inference.hdf",
        ]

        submit_description = {
            "executable": command[0],
            "arguments": " ".join(command[1:]),
            "output": f"{out_base}.out",
            "error": f"{out_base}.err",
            "log": f"{out_base}.log",
            "request_cpus": str(command[command.index("--nprocesses") + 1]) if "--nprocesses" in command else "1",
            "environment": "HDF5_USE_FILE_LOCKING=FALSE OMP_NUM_THREADS=1 OMP_PROC_BIND=false",
            "getenv": "CONDA_EXE,USER,LAL*,PATH,HOME",
            "batch_name": f"PyCBC/{self.production.event.name}/{self.production.name}",
            "request_memory": "8192MB",
            "request_disk": "8192MB",
            "+flock_local": "True",
            "+DESIRED_Sites": htcondor.classad.quote("nogrid"),
            "should_transfer_files": "YES",
            "when_to_transfer_output": "ON_EXIT_OR_EVICT",
            "transfer_output_files": ",".join(transfer_files),
        }

        # Optional accounting info
        accounting = self.production.meta.get("scheduler", {}).get("accounting group")
        if accounting:
            if asimov_config:
                submit_description["accounting_group_user"] = asimov_config.get("condor", "user")
            submit_description["accounting_group"] = accounting

        # Queue job
        hostname_job = htcondor.Submit(submit_description)

        try:
            # Use configured schedd if present
            if asimov_config:
                schedulers = htcondor.Collector().locate(
                    htcondor.DaemonTypes.Schedd, asimov_config.get("condor", "scheduler")
                )
                schedd = htcondor.Schedd(schedulers)
            else:
                raise Exception("No asimov config available")
        except Exception:
            schedd = htcondor.Schedd()

        with schedd.transaction() as txn:
            cluster_id = hostname_job.queue(txn)

        # Record job id
        self.production.job_id = cluster_id
        self.logger.info(f"Submitted PyCBC job: {cluster_id}")
        return cluster_id

    def collect_assets(self):
        """
        Collect all of the output assets for this job.
        """
        assets = {}
        rundir = getattr(self.production, "rundir", None)
        if rundir and os.path.isdir(rundir):
            for fname in [
                "posterior_samples.h5",
                "inference.hdf",
                f"{self.production.name}.log",
            ]:
                fpath = os.path.join(rundir, fname)
                if os.path.exists(fpath):
                    assets[fname] = fpath
        return assets

    def samples(self):
        """
        Collect the combined samples file for PESummary.
        """
        rundir = getattr(self.production, "rundir", None)
        if not rundir:
            return []
        candidates = [
            os.path.join(rundir, "posterior_samples.h5"),
            os.path.join(rundir, "inference.hdf"),
        ]
        return [p for p in candidates if os.path.exists(p)]

    def after_completion(self):
        """
        A hook to be run after the pipeline is detected to have completed.
        """
        self.production.status = "finished"

    def collect_logs(self):
        """
        Collect all of the log files produced by this pipeline and return their contents as a dictionary.
        """
        logs = {}
        rundir = getattr(self.production, "rundir", None)
        if not rundir:
            return logs
        for fname in [f"{self.production.name}.out", f"{self.production.name}.err", f"{self.production.name}.log"]:
            fpath = os.path.join(rundir, fname)
            if os.path.exists(fpath):
                try:
                    with open(fpath, "r") as fh:
                        logs[fname] = fh.read()
                except Exception:
                    continue
        return logs

    def check_progress(self):
        """
        Return the progress of this job.
        """
        return {"completed": self.detect_completion()}

    def read_ini(self):
        """
        Read and parse a configuration file for this pipeline.
        """
        ini = os.path.join(self.production.rundir or ".", f"{self.production.name}.ini")
        parser = Pipeline.read_ini(ini)
        self._validate_ini(parser)
        return parser

    def _validate_ini(self, parser):
        """Minimal validation of required sections/keys for pycbc_inference."""
        required_sections = ["data", "sampler", "model", "variable_params", "static_params"]
        missing = [s for s in required_sections if not parser.has_section(s)]
        if missing:
            raise ValueError(f"Missing sections in PyCBC ini: {missing}")
        # Check a few critical keys
        if not parser.has_option("data", "instruments"):
            raise ValueError("[data] instruments is required")
        if not parser.has_option("sampler", "name"):
            raise ValueError("[sampler] name is required")

    def resurrect(self):
        """
        Attempt to fix and restart a stuck or failed job.
        """
        # Placeholder: no automatic resurrection implemented yet.
        return False
