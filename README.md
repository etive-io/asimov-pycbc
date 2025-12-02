# asimov-pycbc

An Asimov plugin for running PyCBC Inference parameter estimation on HTCondor clusters.

## Overview

This plugin enables [Asimov](https://github.com/lscsoft/asimov) to submit and manage `pycbc_inference` jobs for gravitational wave parameter estimation. It provides:

- **Configuration templating**: Generates `pycbc_inference` config files using Liquid templates with dynamic field population from analysis metadata
- **HTCondor integration**: Submits jobs to HTCondor schedulers with appropriate resource requests and output transfer
- **Status tracking**: Monitors job completion via output file detection
- **Asset management**: Collects posterior samples, logs, and other artifacts


## Contributing

Contributions welcome! Please submit issues or pull requests to the [Asimov Pipelines repository](https://git.ligo.org/asimov/pipelines/pycbc).

## License

This project follows the licensing of the parent Asimov project.
