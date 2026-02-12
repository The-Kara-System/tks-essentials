import os
import pathlib
import pytest
import socket
import yaml
from pathlib import Path
from tksessentials import utils


@pytest.fixture
def mock_project_root(monkeypatch, tmp_path):
    """Fixture to set up a mock project root directory."""
    # Directly set the PROJECT_ROOT in the utils module
    utils.PROJECT_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def mock_app_config(monkeypatch, tmp_path):
    """Fixture to create a mock app_config.yaml file."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    mock_config_file = config_dir / "app_config.yaml"

    # Write the mock configuration
    config = {
        "application": "test-app-name",
        "domain": "test-domain-name",
        "logging_level": "INFO"
    }
    with open(mock_config_file, "w") as file:
        yaml.dump(config, file)

    # Override the find_project_root function
    def mock_find_project_root(*args, **kwargs):
        return tmp_path

    monkeypatch.setattr(utils, "find_project_root", mock_find_project_root)
    return config


# --- Tests for path-related functions ---

def test_get_project_root(mock_project_root):
    """Test getting project root as string."""
    expected_path = str(mock_project_root)
    assert utils.get_project_root() == expected_path


def test_get_project_root_path(mock_project_root):
    """Test getting project root as Path object."""
    assert utils.get_project_root_path() == mock_project_root
    assert isinstance(utils.get_project_root_path(), Path)


def test_get_log_path(mock_project_root):
    """Test getting logs directory path."""
    expected_path = mock_project_root / "logs"
    assert utils.get_log_path() == expected_path
    assert isinstance(utils.get_log_path(), Path)


def test_get_secrets_path(mock_project_root):
    """Test getting secrets directory path."""
    expected_path = mock_project_root / "secrets"
    assert utils.get_secrets_path() == expected_path
    assert isinstance(utils.get_secrets_path(), Path)


# --- Tests for find_project_root function ---

def test_find_project_root_with_env_var(monkeypatch, tmp_path):
    """Test find_project_root uses PROJECT_ROOT environment variable."""
    # First clear any existing PROJECT_ROOT env var, then set it
    monkeypatch.delenv("PROJECT_ROOT", raising=False)
    test_path = str(tmp_path)
    monkeypatch.setenv("PROJECT_ROOT", test_path)
    
    result = utils.find_project_root(pathlib.Path(__file__).resolve())
    assert result == tmp_path


def test_find_project_root_with_config_dir(monkeypatch, tmp_path):
    """Test find_project_root finds config directory."""
    # Ensure PROJECT_ROOT env var is not set
    monkeypatch.delenv("PROJECT_ROOT", raising=False)
    # Create config directory
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    
    result = utils.find_project_root(tmp_path)
    assert result == tmp_path


def test_find_project_root_with_logs_dir(monkeypatch, tmp_path):
    """Test find_project_root finds logs directory."""
    # Ensure PROJECT_ROOT env var is not set
    monkeypatch.delenv("PROJECT_ROOT", raising=False)
    # Create logs directory
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    
    result = utils.find_project_root(tmp_path)
    assert result == tmp_path


def test_find_project_root_searches_parent(monkeypatch, tmp_path):
    """Test find_project_root searches parent directories."""
    # Ensure PROJECT_ROOT env var is not set
    monkeypatch.delenv("PROJECT_ROOT", raising=False)
    # Create nested structure: tmp_path/config and tmp_path/subdir
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    
    result = utils.find_project_root(subdir)
    assert result == tmp_path


def test_find_project_root_failure(monkeypatch, tmp_path):
    """Test find_project_root raises error when marker not found."""
    # Ensure PROJECT_ROOT env var is not set
    monkeypatch.delenv("PROJECT_ROOT", raising=False)
    # Create a deep directory without config or logs
    deep_dir = tmp_path / "a" / "b" / "c" / "d" / "e"
    deep_dir.mkdir(parents=True)
    
    with pytest.raises(FileNotFoundError) as exc_info:
        utils.find_project_root(deep_dir, max_depth=3)
    
    assert "Could not find the project root" in str(exc_info.value)


def test_find_project_root_from_actual_tests_dir(monkeypatch):
    """Test find_project_root works from actual tests directory."""
    # Allow PROJECT_ROOT env var if set (common in CI)
    try:
        project_root = utils.find_project_root(pathlib.Path(__file__).resolve())
        assert project_root.exists()
        # In CI environment, config/logs might not exist if PROJECT_ROOT is set
        # Just verify we got a valid path
        assert isinstance(project_root, pathlib.Path)
    except FileNotFoundError as e:
        pytest.fail(f"find_project_root() raised FileNotFoundError: {e}")


# --- Tests for app_config functions ---

def test_get_app_config_success(mock_app_config, monkeypatch, tmp_path):
    """Test successful loading of app_config.yaml."""
    # Mock os.getcwd to return tmp_path
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    
    result = utils.get_app_config()
    assert result == mock_app_config
    assert result["application"] == "test-app-name"
    assert result["domain"] == "test-domain-name"


def test_get_app_config_missing_file(monkeypatch, tmp_path):
    """Test get_app_config raises error when config file missing."""
    # Create config dir but no file
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    
    def mock_find_project_root(*args, **kwargs):
        return tmp_path
    
    monkeypatch.setattr(utils, "find_project_root", mock_find_project_root)
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    
    with pytest.raises(FileNotFoundError):
        utils.get_app_config()


def test_get_app_config_invalid_yaml(monkeypatch, tmp_path):
    """Test get_app_config handles invalid YAML."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "app_config.yaml"
    
    # Write invalid YAML
    with open(config_file, "w") as f:
        f.write("invalid: yaml: content: [\n")
    
    def mock_find_project_root(*args, **kwargs):
        return tmp_path
    
    monkeypatch.setattr(utils, "find_project_root", mock_find_project_root)
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    
    with pytest.raises(FileNotFoundError) as exc_info:
        utils.get_app_config()
    
    assert "Failed to load the config/app_config.yaml file" in str(exc_info.value)


# --- Tests for application name functions ---

def test_get_application_name_success(monkeypatch):
    """Test successful retrieval of application name."""
    def mock_get_app_config():
        return {"application": "TestApp"}

    monkeypatch.setattr(utils, "get_app_config", mock_get_app_config)
    assert utils.get_application_name() == "TestApp"


def test_get_application_name_with_hyphens(monkeypatch):
    """Test application name replaces hyphens with underscores."""
    def mock_get_app_config():
        return {"application": "test-app-name"}

    monkeypatch.setattr(utils, "get_app_config", mock_get_app_config)
    assert utils.get_application_name() == "test_app_name"


def test_get_application_name_failure(monkeypatch):
    """Test get_application_name raises error when key missing."""
    def mock_get_app_config():
        return {}

    monkeypatch.setattr(utils, "get_app_config", mock_get_app_config)
    
    with pytest.raises(ValueError) as exc_info:
        utils.get_application_name()
    
    assert "Application name not found" in str(exc_info.value)


# --- Tests for domain name functions ---

def test_get_domain_name_success(monkeypatch):
    """Test successful retrieval of domain name."""
    def mock_get_app_config():
        return {"domain": "test.domain.com"}

    monkeypatch.setattr(utils, "get_app_config", mock_get_app_config)
    assert utils.get_domain_name() == "test.domain.com"


def test_get_domain_name_with_hyphens(monkeypatch):
    """Test domain name replaces hyphens with underscores."""
    def mock_get_app_config():
        return {"domain": "test-domain-name"}

    monkeypatch.setattr(utils, "get_app_config", mock_get_app_config)
    assert utils.get_domain_name() == "test_domain_name"


def test_get_domain_name_failure(monkeypatch):
    """Test get_domain_name raises error when key missing."""
    def mock_get_app_config():
        return {}

    monkeypatch.setattr(utils, "get_app_config", mock_get_app_config)
    
    with pytest.raises(ValueError) as exc_info:
        utils.get_domain_name()
    
    assert "Domain name not found" in str(exc_info.value)


# --- Tests for application identifier ---

def test_get_application_identifier(monkeypatch):
    """Test application identifier combines domain and app name."""
    def mock_get_app_config():
        return {
            "domain": "test-domain",
            "application": "test-app"
        }

    monkeypatch.setattr(utils, "get_app_config", mock_get_app_config)
    result = utils.get_application_identifier()
    assert result == "test_domain_test_app"


# --- Tests for environment functions ---

def test_get_pod_name_with_env_var(monkeypatch):
    """Test get_pod_name returns POD_NAME environment variable."""
    monkeypatch.setenv("POD_NAME", "test-pod-123")
    assert utils.get_pod_name() == "test-pod-123"


def test_get_pod_name_fallback_to_hostname(monkeypatch):
    """Test get_pod_name falls back to hostname when POD_NAME not set."""
    monkeypatch.delenv("POD_NAME", raising=False)
    result = utils.get_pod_name()
    assert result == socket.gethostname()


def test_get_environment_default(monkeypatch):
    """Test get_environment returns DEV by default."""
    monkeypatch.delenv("ENV", raising=False)
    assert utils.get_environment() == "DEV"


def test_get_environment_from_env_var(monkeypatch):
    """Test get_environment reads from ENV variable."""
    monkeypatch.setenv("ENV", "PROD")
    assert utils.get_environment() == "PROD"


@pytest.mark.parametrize("env_value", ["DEV", "TEST", "STAGING", "PROD"])
def test_get_environment_various_values(monkeypatch, env_value):
    """Test get_environment with various environment values."""
    monkeypatch.setenv("ENV", env_value)
    assert utils.get_environment() == env_value


# --- Tests for service URL functions ---

def test_get_service_url_default(monkeypatch):
    """Test get_service_url returns default localhost URL."""
    monkeypatch.delenv("OPENAPI_SERVICE_URL", raising=False)
    assert utils.get_service_url() == "http://localhost:8080"


def test_get_service_url_from_env_var(monkeypatch):
    """Test get_service_url reads from environment variable."""
    monkeypatch.setenv("OPENAPI_SERVICE_URL", "https://api.example.com")
    assert utils.get_service_url() == "https://api.example.com"


def test_get_service_doc_url(monkeypatch):
    """Test get_service_doc_url appends /docs to service URL."""
    test_url = "https://api.example.com"
    monkeypatch.setenv("OPENAPI_SERVICE_URL", test_url)
    result = utils.get_service_doc_url()
    assert result == f"{test_url}/docs", f"Expected {test_url}/docs but got {result}"


def test_get_service_doc_url_default(monkeypatch):
    """Test get_service_doc_url with default service URL."""
    monkeypatch.delenv("OPENAPI_SERVICE_URL", raising=False)
    result = utils.get_service_doc_url()
    assert result == "http://localhost:8080/docs", f"Expected http://localhost:8080/docs but got {result}"


# --- Tests for logging level functions ---

def test_get_logging_level_from_config(monkeypatch):
    """Test get_logging_level reads from app config."""
    def mock_get_app_config():
        return {"logging_level": "DEBUG"}

    monkeypatch.setattr(utils, "get_app_config", mock_get_app_config)
    assert utils.get_logging_level() == "DEBUG"


def test_get_logging_level_from_env_var(monkeypatch):
    """Test get_logging_level falls back to LOGGING_LEVEL env var."""
    def mock_get_app_config():
        return {}

    monkeypatch.setattr(utils, "get_app_config", mock_get_app_config)
    monkeypatch.setenv("LOGGING_LEVEL", "WARNING")
    
    assert utils.get_logging_level() == "WARNING"


def test_get_logging_level_default(monkeypatch):
    """Test get_logging_level defaults to DEBUG."""
    def mock_get_app_config():
        return {}

    monkeypatch.setattr(utils, "get_app_config", mock_get_app_config)
    monkeypatch.delenv("LOGGING_LEVEL", raising=False)
    
    assert utils.get_logging_level() == "DEBUG"


def test_get_logging_level_uppercase(monkeypatch):
    """Test get_logging_level returns uppercase."""
    def mock_get_app_config():
        return {"logging_level": "info"}

    monkeypatch.setattr(utils, "get_app_config", mock_get_app_config)
    assert utils.get_logging_level() == "INFO"


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
def test_get_logging_level_various_levels(monkeypatch, level):
    """Test get_logging_level with various log levels."""
    def mock_get_app_config():
        return {"logging_level": level}

    monkeypatch.setattr(utils, "get_app_config", mock_get_app_config)
    assert utils.get_logging_level() == level


# --- Tests for module initialization ---

def test_initialize_project_root(monkeypatch, tmp_path):
    """Test initialize_project_root sets global PROJECT_ROOT."""
    # Save original value
    original_root = utils.PROJECT_ROOT
    
    try:
        # Create a test structure
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        
        # Mock the module directory
        monkeypatch.setattr(os.path, "dirname", lambda x: str(tmp_path))
        monkeypatch.setattr(os.path, "abspath", lambda x: str(tmp_path))
        
        # Call initialize
        utils.initialize_project_root()
        
        # Verify PROJECT_ROOT was set
        assert utils.PROJECT_ROOT is not None
        assert isinstance(utils.PROJECT_ROOT, pathlib.Path)
    finally:
        # Restore original value
        utils.PROJECT_ROOT = original_root
