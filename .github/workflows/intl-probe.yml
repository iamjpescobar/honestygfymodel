name: International Source Probe

on:
  workflow_dispatch: {}   # run manually from the Actions tab — no schedule, no deploys

jobs:
  probe:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install requests

      - name: Probe KBO + NPB sources
        run: python intl_probe.py

      - name: Sample chosen sources (structure recon)
        run: python intl_sample.py