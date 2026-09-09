asimov-pycbc
=============

``asimov-pycbc`` is a plugin for `Asimov <https://asimov.docs.ligo.org/asimov/>`_ 0.7+
that integrates `PyCBC Inference <http://pycbc.org/pycbc/latest/html/inference.html>`_
parameter estimation. Once installed, the plugin is discovered automatically via
Asimov's entry-point registry -- no extra configuration is required.

**What it does**

* Renders a ``pycbc_inference`` config file from a production's meta-data (waveform,
  data, sampler, likelihood), using this plugin's bundled
  :attr:`config_template <asimov_pycbc.pycbc.PyCBC.config_template>` -- or picks up a
  hand-written ``.ini`` already committed to the event repository.
* Submits ``pycbc_inference`` to an HTCondor or Slurm scheduler via Asimov's
  scheduler-agnostic API.
* Once the run completes, advertises its samples (via ``collect_assets()``) for any
  downstream production that declares a ``needs:`` dependency on it -- for example a
  `asimov-pesummary <https://github.com/etive-io/asimov-pesummary>`_ post-processing
  production. This plugin does not submit that job itself; see *Post-processing*
  below.
* Resubmits a failed or evicted job so it resumes from ``pycbc_inference``'s own
  checkpoint, rather than restarting from scratch.

Installation
------------

PyCBC Inference itself must be installed separately (e.g. via conda-forge) -- this
plugin shells out to the ``pycbc_inference`` executable rather than importing
``pycbc``, so it isn't pulled in as a Python dependency:

.. code-block:: bash

   conda install -c conda-forge pycbc "dynesty<2"
   pip install asimov-pycbc

From source:

.. code-block:: bash

   conda install -c conda-forge pycbc "dynesty<2"
   git clone https://github.com/etive-io/asimov-pycbc.git
   cd asimov-pycbc
   pip install -e ".[docs,test]"

.. note::

   ``dynesty<2`` is required: PyCBC's ``dynesty`` sampler backend
   (``pycbc.inference.sampler.dynesty``) imports ``dynesty.nestedsamplers``, a module
   removed in ``dynesty`` 2.0. This isn't PyCBC-Inference-specific -- pin it if you plan
   to use the ``dynesty`` sampler at all.

Tutorial: from a fresh project to posterior samples
----------------------------------------------------

This walks through a complete, runnable example -- an event with simulated
(``--fake-strain``) noise, so no real strain data or datafind access is required. It's
the same configuration this plugin's own end-to-end test (``.github/workflows/e2e.yml``)
runs for real. Swap in real ``data`` metadata (see *Data* below) for an actual analysis.

1. Create a project and point Asimov at your PyCBC environment:

   .. code-block:: bash

      asimov init "Tutorial Project"
      cd "Tutorial Project"
      asimov configuration update pipelines/environment "$CONDA_PREFIX"

2. Apply an event:

   .. code-block:: yaml

      # event.yaml
      kind: event
      name: GW150914
      interferometers:
        - H1
      event time: 1126259462.4

   .. code-block:: bash

      asimov apply -f event.yaml

3. Apply a ``pycbc`` production. This one uses simulated noise, so it needs no
   upstream data-retrieval step:

   .. code-block:: yaml

      # pycbc-production.yaml
      kind: analysis
      name: pycbc-test
      pipeline: pycbc
      status: ready
      waveform:
        approximant: IMRPhenomD
        reference frequency: 30
      likelihood:
        sample rate: 2048
        minimum frequency:
          H1: 30
      data:
        fake strain: aLIGOZeroDetHighPower
        fake strain seed: 1234
      sampler:
        sampler: dynesty
        sampler kwargs:
          nlive: 50
          dlogz: 5.0
      scheduler:
        accounting group: ligo.dev.o4.cbc.pe.pycbc

   .. code-block:: bash

      asimov apply -f pycbc-production.yaml -e GW150914
      asimov manage build submit

   ``manage build`` renders ``pycbc-test.ini`` from this plugin's bundled
   :attr:`config_template <asimov_pycbc.pycbc.PyCBC.config_template>` (unless one
   already exists in the event repository), and ``submit`` submits it.

4. Wait for it to finish (a few seconds to a few minutes, depending on sampler
   settings), checking status with:

   .. code-block:: bash

      asimov monitor

   Once finished, the posterior samples live at
   ``working/GW150914/pycbc-test/pycbc-test.hdf``.

5. Chain a PESummary post-processing step onto it as its own production, with a
   ``needs:`` dependency on ``pycbc-test``:

   .. code-block:: yaml

      # pesummary-production.yaml
      kind: analysis
      name: pycbc-test-pesummary
      pipeline: pesummary
      status: ready
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

   .. code-block:: bash

      asimov apply -f pesummary-production.yaml -e GW150914
      asimov manage build submit

   You can apply this at any point, even before ``pycbc-test`` has finished --
   Asimov's own dependency resolution won't actually build and submit
   ``pycbc-test-pesummary`` until ``pycbc-test`` reaches ``finished``, at which point
   PESummary picks up its samples through ``pycbc-test``'s ``collect_assets()`` (via
   ``production._previous_assets()``), with no glue code of any kind needed from this
   plugin. Keep running ``asimov monitor`` to drive both productions through to
   completion; PESummary's output pages land under Asimov's configured webroot.

   ``summarypages`` (from the real ``pesummary`` package) needs to be able to
   ``import pycbc`` to read ``pycbc_inference``'s native HDF5 format, so install
   ``asimov-pesummary`` into the *same* environment as ``pycbc`` itself -- if it's
   installed anywhere ``pycbc`` isn't importable, reading the samples will fail with
   ``Unable to find a posterior samples table``.

   .. note::

      An earlier version of this plugin submitted the PESummary job automatically
      from ``after_completion()``, by looking up the ``pesummary`` pipeline via
      Asimov's entry-point registry. That approach is no longer used: this plugin's
      ``after_completion()`` now only marks the production ``finished`` --
      post-processing is always expressed as an explicit, dependency-linked
      production, as above.

Data
----

Strain data is read from a production's ``data`` meta-data, using the same
conventions as the sibling GW pipeline plugins (``asimov-lalinference``,
``asimov-bayeswave``) and `asimov-gwdata <https://github.com/etive-io/asimov-gwdata>`_:

.. code-block:: yaml

   data:
     channels:
       H1: H1:DCS-CALIB_STRAIN_CLEAN_C01
       L1: L1:DCS-CALIB_STRAIN_CLEAN_C01
     frame types:
       H1: H1_HOFT_C01
       L1: L1_HOFT_C01

or, with a pre-built LAL-format cache instead of a datafind lookup:

.. code-block:: yaml

   data:
     cache files:
       H1: /path/to/H1.cache
       L1: /path/to/L1.cache

Because these are the same ``data.*`` keys ``asimov-gwdata`` writes, a ``pycbc``
production listed after a ``gwdata`` production in the same event (or made to
``needs:`` it) picks up real frame data automatically -- ``data-retrieval -> pycbc ->
pesummary`` is expressed entirely through Asimov's own dependency mechanism, with no
extra glue code.

Status messages
~~~~~~~~~~~~~~~~

``wait``
   The pipeline will ignore the production.

``ready``
   Asimov will attempt to submit the job to the scheduler.

``running``
   Applied after the job is submitted to the cluster.

``stuck``
   Applied when the job is held or an error is detected in the pipeline's execution.

``finished``
   Applied when normal termination of the pipeline is detected (a real, readable
   posterior HDF5 file exists). This is a terminal state as far as this plugin is
   concerned -- see *Post-processing* below for what (if anything) happens next.

Post-processing
----------------

This plugin does not run any post-processing itself, and ``after_completion()``
does nothing beyond marking the production ``finished``. Instead, post-processing
(PESummary or otherwise) is expressed as its own, separate production with a
``needs:`` dependency on the ``pycbc`` production -- see step 5 of the tutorial
above. Asimov's own dependency resolution is what actually builds and submits that
production once this one finishes; this plugin only needs to make its samples
available via ``collect_assets()``, which it always does regardless of whether
anything ever consumes them.

.. toctree::
   :maxdepth: 2
   :caption: Reference

   api
