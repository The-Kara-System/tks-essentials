# Testing Guide

## Overview

This project has comprehensive unit tests with 100% coverage for the core utility modules.

## Test Structure

### Test Files

- **tests/test_utils.py** - 41 tests covering all functions in `tksessentials/utils.py`
- **tests/test_validators.py** - 65 tests covering all functions in `tksessentials/validators.py`

### Coverage Summary

- `tksessentials/utils.py`: **100% coverage**
- `tksessentials/validators.py`: **100% coverage**

## Testing Best Practices Implemented

### 1. Comprehensive Test Coverage

#### utils.py Tests Include:
- **Path Management**: Project root, logs path, secrets path
- **Configuration Loading**: YAML parsing, error handling for missing/invalid configs
- **Environment Variables**: POD_NAME, ENV, OPENAPI_SERVICE_URL, LOGGING_LEVEL
- **Application Metadata**: Domain names, application names, identifiers
- **Edge Cases**: Missing values, hyphen replacement, fallback values

#### validators.py Tests Include:
- **Email Validation**: Valid emails (Gmail, Yahoo, Outlook), invalid formats, deliverability checks
- **IP Address Validation**: IPv4, IPv6, invalid formats, edge cases
- **Type Safety**: Non-string inputs, None values, type errors

### 2. Pytest Best Practices

- **Fixtures**: Reusable test setups with `@pytest.fixture`
- **Parametrization**: `@pytest.mark.parametrize` for testing multiple inputs
- **Mocking**: `monkeypatch` for environment variables and function mocking
- **Temp Files**: `tmp_path` fixture for isolated file system tests
- **Descriptive Names**: Clear test function names describing what is tested

### 3. Test Organization

```
tests/
├── test_utils.py          # 41 tests for utility functions
├── test_validators.py     # 65 tests for validation functions
├── conftest.py           # Shared fixtures and configuration
└── docker-compose.yaml   # Kafka/ksqlDB for integration tests
```

## Running Tests

### Run All Tests

```bash
pytest
```

`pytest` includes coverage reporting by default in this project.

### Run Specific Test Files

```bash
pytest tests/test_utils.py tests/test_validators.py
```

### Run with Coverage

```bash
pytest
```

### Run Verbose

```bash
pytest -v
```

### Run with Output

```bash
pytest -s -vv
```

## GitHub Actions Integration

The project uses GitHub Actions for automated testing on every push to `main`.

### Workflow: `.github/workflows/testing_and_deployment.yml`

**Testing Steps:**
1. Checkout code
2. Set up Python 3.12.9
3. Install system dependencies (Docker, librdkafka)
4. Install Python dependencies
5. Start Kafka and ksqlDB (for integration tests)
6. Run pytest with coverage
7. Upload coverage reports as artifacts

**Deployment Steps:**
1. Build package after tests pass
2. Bump version automatically
3. Publish to PyPI

### Coverage Reports

Coverage reports are uploaded as artifacts after each test run:
- Available for 30 days
- HTML format for easy viewing
- Shows line-by-line coverage

## Adding New Tests

### For New Utility Functions

1. Add function to `tksessentials/utils.py`
2. Add tests to `tests/test_utils.py`:
   ```python
   def test_new_function(monkeypatch):
       """Test description."""
       # Setup
       monkeypatch.setenv("VAR", "value")
       
       # Execute
       result = utils.new_function()
       
       # Assert
       assert result == expected_value
   ```

### For New Validators

1. Add validator to `tksessentials/validators.py`
2. Add tests to `tests/test_validators.py`:
   ```python
   @pytest.mark.parametrize("input_value", ["valid1", "valid2"])
   def test_valid_inputs(input_value):
       """Test valid inputs."""
       validators.validate_something(input_value)
   
   @pytest.mark.parametrize("input_value", ["invalid1", "invalid2"])
   def test_invalid_inputs(input_value):
       """Test invalid inputs raise errors."""
       with pytest.raises(ValueError):
           validators.validate_something(input_value)
   ```

## Key Testing Patterns

### 1. Testing Environment Variables

```python
def test_with_env_var(monkeypatch):
    monkeypatch.setenv("VAR_NAME", "value")
    result = function_that_uses_env_var()
    assert result == expected

def test_without_env_var(monkeypatch):
    monkeypatch.delenv("VAR_NAME", raising=False)
    result = function_with_fallback()
    assert result == default_value
```

### 2. Testing File Operations

```python
def test_file_loading(tmp_path):
    # Create test file
    test_file = tmp_path / "config.yaml"
    test_file.write_text("key: value")
    
    # Test loading
    result = load_config(test_file)
    assert result["key"] == "value"
```

### 3. Testing Error Conditions

```python
def test_error_handling(monkeypatch):
    def mock_function():
        return {}
    
    monkeypatch.setattr(module, "function", mock_function)
    
    with pytest.raises(ValueError) as exc_info:
        function_that_should_fail()
    
    assert "expected error message" in str(exc_info.value)
```

## Bug Fixes Found During Testing

While implementing comprehensive tests, we discovered and fixed:

1. **utils.py line 103**: `get_service_doc_url()` was missing parentheses when calling `get_service_url`, returning the function object instead of calling it.

This demonstrates the value of comprehensive testing in catching bugs early!

## Continuous Improvement

- Monitor coverage reports after each push
- Add tests for any new features before merging
- Ensure all tests pass in CI before deployment
- Keep test runtime under 30 seconds for fast feedback
