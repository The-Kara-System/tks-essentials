# tks-essentials
A library with essentials needed in every backend python app. e.g. logging, local db connection, filtering, formatting etc.

## Sponsors
Freya Alpha,
The Kára System,
Spark & Hale Robotic Industries

## General
Run and compiled for Python 3.9.13.
Expected to run for Python 3+

## Development

### Testing
run tests with `pytest -s -vv` to see all the details.

### Installation as Consuming Developer

Simply run: `pip install tks-essentials`

Import in modules without the dash (e.g.): `from tksessentials.globallogger import GlobalLogger`

### Setup as Contributor
Create the virtul environment: 
```
py -m venv .venv
```
Start the Environment: 
```
./.venv/Scripts/activate
```
 (or allow VS Code to start it). Use `deactivate`to stop it.

All the required libraries must be listed in requirements.txt and installed by  
```
python -m pip install -r .\requirements.txt
```
For Dev use 
```
python -m pip install -r .\requirements-dev.txt
```

To cleanup the environment run:
```
pip3 freeze > to-uninstall.txt
```
 and then
```
pip3 uninstall -y -r to-uninstall.txt
```

or 
```
pip3 install pip-autoremove
```

### Testing
Before running the tests, make sure that the utils.py can find the root directory. Either set the PROJECT_ROOT environement variable to the root directory, or simply create a config or a logs directory within the project root. Then run the pytests. 

### Build Library
Prerequisite: make sure that you give your Operating System user the right to modify files in the python directory. The directory where pyhton is installed.
Use 
```python setup.py bdist_wheel```
 to create the dist, build and .eggs folder.


## Releasing a new version / CICD Process

This is entirely executed with Github Actions.

Visual Studio Code --> GitHub Actions --> Build within Github Actions --> Uploaded by Github Actions to pypi.org.