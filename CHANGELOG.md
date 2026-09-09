# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- `after_completion()` no longer looks up and submits the `pesummary`
  pipeline itself via the `asimov.pipelines` entry-point group. Asimov's
  newer convention for chaining pipelines is a separate, explicit
  production with a `needs:` dependency (resolved by Asimov's own
  dependency graph, not by the upstream pipeline reaching out and
  submitting a job for whatever it thinks should run next) -- see
  [asimov-pesummary](https://github.com/etive-io/asimov-pesummary) and the
  *Post-processing* section of the docs. `STATUS` no longer includes
  `processing` (the status this plugin briefly used while an automatic
  hand-off was in flight); a finished production just stays `finished`.
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
- `collect_assets()` advertises a completed job's samples (and rendered
  config) for any downstream production that declares a `needs:` dependency
  on it -- e.g. an [asimov-pesummary](https://github.com/etive-io/asimov-pesummary)
  post-processing production, resolved entirely by Asimov's own dependency
  graph. `after_completion()` itself does nothing beyond marking the
  production `finished`; it has no knowledge of PESummary or any other
  downstream consumer (see Changed, below, for why this replaced an earlier
  automatic hand-off).
- Checkpoint-aware `resurrect()`: `pycbc_inference` checkpoints its own
  progress to `<output-file>.checkpoint`; a failed/evicted job is
  resubmitted without `--force` so it resumes rather than restarting from
  scratch, up to 5 attempts.
- A genuine end-to-end test (`.github/workflows/e2e.yml`): a real
  `pycbc_inference` job (dynesty, simulated `--fake-strain` Gaussian noise)
  submitted through a real HTCondor scheduler, waiting for a real,
  parseable posterior samples file -- not a smoke test. Then a real
  `asimov-pesummary` production, wired up via `needs:`, that consumes
  those samples through a genuine `summarypages` run and produces a real,
  parseable combined posterior file -- exercising the full dependency-driven
  post-processing hand-off described above, not just the upstream job in
  isolation.
- Unit test suite rewritten around mocked `production`/`config` fixtures
  (mirroring the sibling plugins' test style), plus a test that renders
  `configs/pycbc.ini` through the real Liquid engine -- this caught a real
  templating bug (a trailing `-%}` trim tag was eating the newline before
  the `[data]` section header, corrupting the rendered ini) that a
  file-existence-only check would have missed.

### Removed
- `setup.cfg` (duplicated the `pyproject.toml` entry-point declaration).
