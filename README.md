# tks-essentials

A library with essentials needed in every backend Python app, including logging, local database connection helpers, filtering, and formatting utilities.

## Sponsors

Freya Alpha,
The Kára System,
Spark & Hale Robotic Industries

## Requirements

This package currently requires `Python 3.12.9` or newer.

## Installation

Install from PyPI:

```powershell
python -m pip install tks-essentials
```

Import the package without the dash:

```python
from tksessentials import global_logger
```

## Development

### Setup as Contributor

Create the virtual environment:

```powershell
py -m venv .venv
```

Activate it in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install runtime dependencies:

```powershell
python -m pip install -r .\requirements.txt
```

Install dev dependencies:

```powershell
python -m pip install -r .\requirements-dev.txt
```

`requirements-dev.txt` already includes `requirements.txt`, so the dev file alone is enough for local development and testing.

To clean up the environment:

```powershell
pip3 freeze > to-uninstall.txt
pip3 uninstall -y -r to-uninstall.txt
```

### Testing

Before running tests, make sure `utils.py` can find the project root. Either set the `PROJECT_ROOT` environment variable to the repository root, or create a `config` or `logs` directory there.

Run the unit suite:

```powershell
python -m pytest
```

Integration tests live in `tests/int`. They automatically start the Docker Compose stack in `tests/docker-compose.yaml`, wait for a 3-broker Kafka cluster plus ksqlDB to become ready, and tear the stack down when the test session ends.

Run the integration suite:

```powershell
python -m pytest tests/int
```

If you want unit-test coverage locally:

```powershell
python -m pytest --cov=tksessentials --cov-report=term-missing --cov-report=html --cov-fail-under=80
```

### Build Library

This repository is built from `pyproject.toml`. There is no `setup.py`, so `python setup.py bdist_wheel` is not the correct build command anymore.

Install the build frontend:

```powershell
python -m pip install build
```

Build source and wheel distributions:

```powershell
python -m build
```

Artifacts are written to `dist/`.

Validate the generated packages in PowerShell:

```powershell
$dist = Get-ChildItem .\dist | ForEach-Object { $_.FullName }
python -m twine check $dist
```

## Releasing a New Version / CI/CD Process

GitHub Actions runs the release flow. The workflow installs `.[dev]`, builds with `python -m build`, validates the distributions, and publishes them to PyPI.
