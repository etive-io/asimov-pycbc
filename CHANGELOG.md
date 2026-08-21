# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Rewrote the pipeline to target `asimov>=0.7`. The previous implementation
  overrode `Pipeline.__init__` without calling `super().__init__()`, so
  `self.logger` was never set -- every method that logged (almost all of
  them) raised `AttributeError` as soon as it ran through Asimov's own
  machinery, a bug entirely masked by a unit test suite built from mocks
  that never exercised construction through `asimov apply`/`manage build`.
- `submit_dag()` now submits jobs through Asimov's scheduler abstraction
  (`self.scheduler.submit(...)`, backed by `asimov.scheduler_utils`) instead
  of importing `htcondor`/`htcondor2` and talking to a schedd directly. This
  gets Slurm support for free and matches the pattern already adopted by
  the sibling `asimov-lalinference`/`asimov-bayeswave`/`asimov-pesummary`
  plugins.
- Dropped the hard `pycbc>=2.2` PyPI dependency. Like the sibling plugins,
  this package shells out to the `pycbc_inference` executable rather than
  importing `pycbc`, so the (heavyweight, conda-oriented) PyCBC install is
  no longer a pip dependency of the thin Asimov plugin itself.
- Rewrote the bundled `configs/pycbc.ini` Liquid template to use the same
  `production.meta` key conventions as the sibling plugins (`data.channels`
  / `data.frame types` / `data.cache files` / `data.frame files`,
  `likelihood.minimum frequency`, `likelihood.sample rate`,
  `waveform.approximant`), including support for `data.fake strain`
  (PyCBC's built-in simulated-noise mode).

### Added
- `config_template` property (`asimov_pycbc/configs/pycbc.ini`), pointing at
  a real bundled Liquid template, so `asimov manage build` can render a
  production's `.ini` directly from ledger metadata.
- `after_completion()` hands a completed job's samples off to the
  `asimov-pesummary` plugin (discovered via the `asimov.pipelines`
  entry-point group), matching `asimov-lalinference`'s approach. Raises a
  clear `PipelineException` (rather than an opaque failure) when
  `asimov-pesummary` isn't installed.
- Checkpoint-aware `resurrect()`: `pycbc_inference` checkpoints its own
  progress to `<output-file>.checkpoint`; a failed/evicted job is
  resubmitted without `--force` so it resumes rather than restarting from
  scratch, up to 5 attempts.
- A genuine end-to-end test (`.github/workflows/e2e.yml`): a real
  `pycbc_inference` job (dynesty, simulated `--fake-strain` Gaussian noise)
  submitted through a real HTCondor scheduler, waiting for a real,
  parseable posterior samples file -- not a smoke test. Also
  regression-checks that the PESummary hand-off fails cleanly (a clear
  `PipelineException`, not a crash) when `asimov-pesummary` isn't
  installed.
- Unit test suite rewritten around mocked `production`/`config` fixtures
  (mirroring the sibling plugins' test style), plus a test that renders
  `configs/pycbc.ini` through the real Liquid engine -- this caught a real
  templating bug (a trailing `-%}` trim tag was eating the newline before
  the `[data]` section header, corrupting the rendered ini) that a
  file-existence-only check would have missed.

### Removed
- `setup.cfg` (duplicated the `pyproject.toml` entry-point declaration).
