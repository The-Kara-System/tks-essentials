from email_validator import EmailSyntaxError, EmailNotValidError
import pytest
from tksessentials import validators


# --- Email Validation Tests ---

@pytest.mark.parametrize("email", [
    "john.doe@gmail.com",
    "user@yahoo.com",
    "test.email@outlook.com",
])
def test_valid_email_addresses(email):
    """Test that valid email addresses pass validation with real domains."""
    try:
        validators.validate_email(email)
    except (EmailSyntaxError, EmailNotValidError):
        pytest.fail(f"validate_email() raised exception unexpectedly for valid email: {email}")


@pytest.mark.parametrize("email", [
    "name@com",  # TLD too short
    "@domain.com",  # Missing local part
    "name@domain",  # Missing TLD
    "firstname.name@DOMAIN-THAT-PROBABLY-WILL-NEVER-EXIST-TEST-0123.com",  # Non-deliverable
    "plainaddress",  # No @ sign
    "@",  # Only @ sign
    "user@",  # Missing domain
    "user name@example.com",  # Space in local part
    "user@domain .com",  # Space in domain
    "user..name@example.com",  # Double dots
    ".user@example.com",  # Starts with dot
    "user.@example.com",  # Ends with dot
    "user@.example.com",  # Domain starts with dot
    "user@example..com",  # Double dots in domain
    "",  # Empty string
    "user@",  # Missing domain part
])
def test_invalid_email_addresses(email):
    """Test that invalid email addresses fail validation."""
    with pytest.raises((EmailSyntaxError, EmailNotValidError, ValueError)):
        validators.validate_email(email)


def test_email_validation_with_none():
    """Test that None input raises an exception."""
    with pytest.raises((TypeError, AttributeError)):
        validators.validate_email(None)


def test_email_validation_case_insensitive():
    """Test that email validation handles case correctly."""
    # Email addresses should be case-insensitive
    try:
        validators.validate_email("User@Gmail.COM")
    except (EmailSyntaxError, EmailNotValidError):
        pytest.fail("validate_email() should accept mixed case emails")


# --- IP Address Validation Tests ---

@pytest.mark.parametrize("ip_address", [
    "100.128.0.0",
    "192.168.1.1",
    "10.0.0.1",
    "172.16.0.1",
    "255.255.255.255",
    "0.0.0.0",
    "127.0.0.1",
    "8.8.8.8",
])
def test_valid_ipv4_addresses(ip_address: str):
    """Test that valid IPv4 addresses pass validation."""
    try:
        validators.validate_ip_address(ip_address)
    except ValueError:
        pytest.fail(f"validate_ip_address() raised exception unexpectedly for valid IP: {ip_address}")


@pytest.mark.parametrize("ip_address", [
    "2001:0db8:85a3:0000:0000:8a2e:0370:7334",  # Full IPv6
    "2001:db8:85a3::8a2e:370:7334",  # Compressed IPv6
    "::1",  # IPv6 loopback
    "fe80::1",  # IPv6 link-local
    "::",  # IPv6 all zeros
    "2001:db8::1",  # Compressed
    "::ffff:192.0.2.1",  # IPv4-mapped IPv6
])
def test_valid_ipv6_addresses(ip_address: str):
    """Test that valid IPv6 addresses pass validation."""
    try:
        validators.validate_ip_address(ip_address)
    except ValueError:
        pytest.fail(f"validate_ip_address() raised exception unexpectedly for valid IPv6: {ip_address}")


@pytest.mark.parametrize("ip_address", [
    None,
    "127 .0.0.1",  # Space in address
    "999.255.255.255",  # Octet out of range
    "100.128.0.0/222",  # CIDR notation (not a single IP)
    "256.1.1.1",  # Octet out of range
    "1.256.1.1",  # Octet out of range
    "1.1.256.1",  # Octet out of range
    "1.1.1.256",  # Octet out of range
    "192.168.1",  # Incomplete address
    "192.168.1.1.1",  # Too many octets
    "192.168.-1.1",  # Negative number
    "abc.def.ghi.jkl",  # Non-numeric
    "192.168.1.1/24",  # CIDR notation
    "",  # Empty string
    "....",  # Only dots
    "192.168.1.1 ",  # Trailing space
    " 192.168.1.1",  # Leading space
    "192.168.1.01",  # Leading zero (ambiguous)
])
def test_invalid_ip_addresses(ip_address: str):
    """Test that invalid IP addresses fail validation."""
    with pytest.raises((ValueError, TypeError)):
        validators.validate_ip_address(ip_address)


def test_ip_validation_with_empty_string():
    """Test that empty string raises ValueError."""
    with pytest.raises(ValueError):
        validators.validate_ip_address("")


def test_ip_validation_with_integer():
    """Test that integer input is accepted by ipaddress library."""
    # ipaddress.ip_address actually accepts integers
    try:
        validators.validate_ip_address(16777216)  # 1.0.0.0 as integer
    except ValueError:
        pytest.fail("ipaddress library accepts integers as valid IP addresses")


def test_ip_validation_with_list():
    """Test that list input raises ValueError."""
    with pytest.raises(ValueError):
        validators.validate_ip_address([192, 168, 1, 1])


# --- Edge Case Tests ---

@pytest.mark.parametrize("input_value", [
    123,
    12.34,
    [],
    {},
    True,
])
def test_email_validation_with_non_string_types(input_value):
    """Test that non-string inputs raise appropriate exceptions."""
    with pytest.raises((TypeError, AttributeError)):
        validators.validate_email(input_value)


def test_email_validation_preserves_exception_info():
    """Test that the original exception information is preserved."""
    try:
        validators.validate_email("invalid@")
    except Exception as e:
        # Should be EmailSyntaxError or EmailNotValidError
        assert isinstance(e, (EmailSyntaxError, EmailNotValidError))


def test_ip_validation_preserves_exception_info():
    """Test that the original exception information is preserved."""
    try:
        validators.validate_ip_address("999.999.999.999")
    except ValueError as e:
        # Should contain meaningful error message
        assert str(e)  # Error message should not be empty
