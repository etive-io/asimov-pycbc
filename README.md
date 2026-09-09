# asimov-pycbc

An [Asimov](https://github.com/asimov-gw/asimov) plugin for running
[PyCBC Inference](http://pycbc.org/pycbc/latest/html/inference.html)
parameter estimation.

📚 **[Full documentation and tutorial](https://etive-io.github.io/asimov-pycbc/)**

## Overview

This plugin enables Asimov to submit and manage `pycbc_inference` jobs for
gravitational wave parameter estimation. It provides:

- **Configuration templating**: renders a `pycbc_inference` config file
  from a bundled Liquid template, populated from a production's ledger
  metadata (`config_template`), for use by `asimov manage build`.
- **Scheduler integration**: submits jobs via Asimov's own scheduler
  abstraction (`self.scheduler`, from `asimov.pipeline.Pipeline` /
  `asimov.scheduler_utils`), which supports both HTCondor and Slurm --
  rather than talking to a scheduler's API directly.
- **Status tracking**: monitors job completion by checking for a genuine,
  readable posterior samples file.
- **Checkpoint-aware resurrection**: `pycbc_inference` checkpoints its own
  progress; a failed or evicted job is resubmitted so it resumes from that
  checkpoint rather than starting over.
- **Dependency-driven post-processing**: once a job completes, its samples are
  available (via `collect_assets()`) to any downstream production with a
  `needs:` dependency on it -- for example an
  [asimov-pesummary](https://github.com/etive-io/asimov-pesummary) production.
  This plugin doesn't submit that job itself; Asimov's own dependency
  resolution does.

## Compatibility

Requires `asimov>=0.7`. This plugin does not depend on the `pycbc` Python
package itself -- like the sibling `asimov-lalinference` and
`asimov-bayeswave` plugins, it shells out to the `pycbc_inference`
executable, which is expected to be installed separately (e.g. via conda)
in the environment pointed at by Asimov's `[pipelines] environment` config
option.

## Installation

```bash
pip install asimov-pycbc
```

For development:
```bash
git clone https://github.com/etive-io/asimov-pycbc
cd asimov-pycbc
pip install -e ".[test]"
```

## Usage

Once installed, Asimov discovers this plugin automatically via its
`asimov.pipelines` entry point. Add a production to an event with
`pipeline: pycbc`:

```yaml
kind: analysis
name: pycbc-imrphenompv2
pipeline: pycbc
waveform:
  approximant: IMRPhenomPv2
  reference frequency: 20
sampler:
  sampler: dynesty
  sampler kwargs:
    nlive: 2000
    dlogz: 0.1
scheduler:
  accounting group: ligo.dev.o4.cbc.pe.pycbc
  processes: 8
```

`asimov manage build submit` will render a `pycbc_inference` ini from the
bundled template (unless one already exists in the event repository) and
submit the job.

### Data

Strain data is read from a production's `data` metadata using the same
conventions as the other Asimov gravitational-wave pipeline plugins (e.g.
`asimov-gwdata`, `asimov-lalinference`, `asimov-bayeswave`):

- `data.frame types` / `data.channels` -- real data via datafind lookup
- `data.cache files` -- a pre-built LAL-format frame cache
- `data.frame files` -- explicit frame file paths
- `data.fake strain` (e.g. `aLIGOZeroDetHighPower`) -- simulated Gaussian
  noise, no real strain data required

This means a production populated by a data-retrieval step (for example
[asimov-gwdata](https://github.com/etive-io/asimov-gwdata), which writes
`data.cache files/data.frame files` into a production's metadata) is picked
up automatically, without any extra wiring: `data-retrieval -> pycbc ->
pesummary` is expressed entirely through Asimov's own `needs:` dependency
mechanism.

### Post-processing

This plugin does not run PESummary (or anything else) itself. When a `pycbc`
production completes, `after_completion()` only marks it `finished` --
post-processing is expressed as a separate production with a `needs:`
dependency on it, e.g.:

```yaml
kind: analysis
name: pycbc-test-pesummary
pipeline: pesummary
needs:
  - pycbc-test
waveform:
  approximant: IMRPhenomD
  reference frequency: 30
  minimum frequency:
    H1: 30
postprocessing:
  pesummary:
    multiprocess: 2
```

Asimov's own dependency resolution builds and submits `pycbc-test-pesummary`
once `pycbc-test` reaches `finished`; PESummary picks up its samples via
`pycbc-test`'s `collect_assets()` (through `production._previous_assets()`).
Install [asimov-pesummary](https://github.com/etive-io/asimov-pesummary) into
the *same* environment as `pycbc` itself -- `summarypages` needs to
`import pycbc` to read `pycbc_inference`'s native HDF5 format.

## Testing

Unit tests (mocked, no external dependencies):

```bash
pip install -e ".[test]"
pytest
```

`.github/workflows/e2e.yml` also runs a genuine end-to-end test: a real
`pycbc_inference` run (using PyCBC's own simulated `--fake-strain` noise so
no real strain data is required) submitted through a real HTCondor
scheduler, waiting for a real, parseable posterior samples file -- then a
real `asimov-pesummary` production, wired up via `needs:`, that consumes
those samples and produces a real, parseable `summarypages` output.

`.github/workflows/docs.yml` also checks that the subcommand and flags used
by every `asimov ...` command shown in `docs/*.rst` still exist on the live,
installed asimov CLI, on every pull request (`scripts/lint_tutorial_commands.py`).
It doesn't validate positional arguments or actually run anything, but it
does mean a renamed subcommand or flag in a future asimov release shows up
as a CI failure here rather than as a tutorial that silently stops working:

```bash
pip install -e .
python scripts/lint_tutorial_commands.py
```

## Contributing

Contributions welcome! Please submit issues or pull requests to
[etive-io/asimov-pycbc](https://github.com/etive-io/asimov-pycbc).

## License

MIT -- see [LICENSE](LICENSE).
