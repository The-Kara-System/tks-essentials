from unittest.mock import Mock

import pytest

from tksessentials import database


KAFKA_ENVIRONMENT_VARIABLES = (
    "KAFKA_BROKER_STRING",
    "KAFKA_SECURITY_PROTOCOL",
    "KAFKA_SASL_MECHANISM",
    "KAFKA_SASL_USERNAME",
    "KAFKA_SASL_PASSWORD_FILE",
    "KAFKA_SSL_CA_FILE",
)

KSQLDB_ENVIRONMENT_VARIABLES = (
    "KSQLDB_STRING",
    "KSQLDB_USERNAME",
    "KSQLDB_PASSWORD_FILE",
    "KSQLDB_CA_FILE",
)


def _clear_environment(monkeypatch, names):
    for name in names:
        monkeypatch.delenv(name, raising=False)


def _set_prod_kafka_environment(monkeypatch, tmp_path):
    password_file = tmp_path / "kafka-password"
    password_file.write_text("secret-password\n", encoding="utf-8")
    ca_file = tmp_path / "kafka-ca.crt"
    ca_file.write_text("test-ca", encoding="utf-8")

    monkeypatch.setattr(database.utils, "get_environment", lambda: "PROD")
    monkeypatch.setenv(
        "KAFKA_BROKER_STRING",
        "sahri-kafka-kafka-bootstrap.sahri-datastorage-prod.svc.cluster.local:9093",
    )
    monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "SASL_SSL")
    monkeypatch.setenv("KAFKA_SASL_MECHANISM", "SCRAM-SHA-512")
    monkeypatch.setenv("KAFKA_SASL_USERNAME", "tks-runtime-prod")
    monkeypatch.setenv("KAFKA_SASL_PASSWORD_FILE", str(password_file))
    monkeypatch.setenv("KAFKA_SSL_CA_FILE", str(ca_file))
    return ca_file


def _set_prod_ksqldb_environment(monkeypatch, tmp_path):
    password_file = tmp_path / "ksqldb-password"
    password_file.write_text("ksql-secret\r\n", encoding="utf-8")
    ca_file = tmp_path / "ksqldb-ca.crt"
    ca_file.write_text("test-ca", encoding="utf-8")

    monkeypatch.setattr(database.utils, "get_environment", lambda: "PROD")
    monkeypatch.setenv(
        "KSQLDB_STRING",
        "https://ksqldb.sahri-datastorage-prod.svc.cluster.local:8088",
    )
    monkeypatch.setenv("KSQLDB_USERNAME", "tks-ksqldb-prod")
    monkeypatch.setenv("KSQLDB_PASSWORD_FILE", str(password_file))
    monkeypatch.setenv("KSQLDB_CA_FILE", str(ca_file))
    return ca_file


def test_kafka_client_kwargs_keep_zero_config_dev_compatible(monkeypatch):
    monkeypatch.setattr(database.utils, "get_environment", lambda: "DEV")
    _clear_environment(monkeypatch, KAFKA_ENVIRONMENT_VARIABLES)

    assert database.get_kafka_client_kwargs() == {
        "bootstrap_servers": "localhost:9092",
        "security_protocol": "PLAINTEXT",
    }


def test_kafka_client_kwargs_build_prod_sasl_ssl_config(monkeypatch, tmp_path):
    ca_file = _set_prod_kafka_environment(monkeypatch, tmp_path)
    ssl_context = object()
    create_default_context = Mock(return_value=ssl_context)
    monkeypatch.setattr(database.ssl, "create_default_context", create_default_context)

    config = database.get_kafka_client_kwargs()

    assert config == {
        "bootstrap_servers": (
            "sahri-kafka-kafka-bootstrap.sahri-datastorage-prod.svc.cluster.local:9093"
        ),
        "security_protocol": "SASL_SSL",
        "sasl_mechanism": "SCRAM-SHA-512",
        "sasl_plain_username": "tks-runtime-prod",
        "sasl_plain_password": "secret-password",
        "ssl_context": ssl_context,
    }
    create_default_context.assert_called_once_with(cafile=str(ca_file.resolve()))


@pytest.mark.parametrize(
    "missing_name",
    (
        "KAFKA_BROKER_STRING",
        "KAFKA_SECURITY_PROTOCOL",
        "KAFKA_SASL_MECHANISM",
        "KAFKA_SASL_USERNAME",
        "KAFKA_SASL_PASSWORD_FILE",
        "KAFKA_SSL_CA_FILE",
    ),
)
def test_kafka_client_kwargs_fail_closed_in_prod(monkeypatch, tmp_path, missing_name):
    _set_prod_kafka_environment(monkeypatch, tmp_path)
    monkeypatch.delenv(missing_name)

    with pytest.raises(ValueError, match=missing_name):
        database.get_kafka_client_kwargs()


def test_kafka_client_kwargs_reject_prod_plaintext(monkeypatch, tmp_path):
    _set_prod_kafka_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")

    with pytest.raises(ValueError, match="SASL_SSL"):
        database.get_kafka_client_kwargs()


def test_kafka_client_kwargs_support_explicit_bootstrap_override(monkeypatch):
    monkeypatch.setattr(database.utils, "get_environment", lambda: "DEV")
    _clear_environment(monkeypatch, KAFKA_ENVIRONMENT_VARIABLES)

    config = database.get_kafka_client_kwargs(["broker-a:9092", "broker-b:9092"])

    assert config["bootstrap_servers"] == "broker-a:9092,broker-b:9092"


def test_ksqldb_httpx_kwargs_keep_zero_config_dev_compatible(monkeypatch):
    monkeypatch.setattr(database.utils, "get_environment", lambda: "DEV")
    _clear_environment(monkeypatch, KSQLDB_ENVIRONMENT_VARIABLES)

    assert database.get_ksqldb_url() == "http://localhost:8088/ksql"
    assert database.get_ksqldb_httpx_kwargs() == {}


def test_ksqldb_httpx_kwargs_build_prod_https_config(monkeypatch, tmp_path):
    ca_file = _set_prod_ksqldb_environment(monkeypatch, tmp_path)
    ssl_context = object()
    create_default_context = Mock(return_value=ssl_context)
    monkeypatch.setattr(database.ssl, "create_default_context", create_default_context)

    config = database.get_ksqldb_httpx_kwargs()

    assert config == {
        "auth": ("tks-ksqldb-prod", "ksql-secret"),
        "verify": ssl_context,
    }
    assert (
        database.get_ksqldb_url(database.KafkaKSqlDbEndPoint.INFO)
        == "https://ksqldb.sahri-datastorage-prod.svc.cluster.local:8088/info"
    )
    create_default_context.assert_called_once_with(cafile=str(ca_file.resolve()))


@pytest.mark.parametrize(
    "missing_name",
    (
        "KSQLDB_STRING",
        "KSQLDB_USERNAME",
        "KSQLDB_PASSWORD_FILE",
        "KSQLDB_CA_FILE",
    ),
)
def test_ksqldb_httpx_kwargs_fail_closed_in_prod(monkeypatch, tmp_path, missing_name):
    _set_prod_ksqldb_environment(monkeypatch, tmp_path)
    monkeypatch.delenv(missing_name)

    with pytest.raises(ValueError, match=missing_name):
        database.get_ksqldb_httpx_kwargs()


def test_ksqldb_rejects_plain_http_in_prod(monkeypatch, tmp_path):
    _set_prod_ksqldb_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("KSQLDB_STRING", "http://ksqldb:8088")

    with pytest.raises(ValueError, match="HTTPS"):
        database.get_ksqldb_httpx_kwargs()


def test_ksqldb_requests_share_auth_and_tls_helper(monkeypatch):
    response = Mock(status_code=200)
    response.json.return_value = {"KsqlServerInfo": {"serverStatus": "RUNNING"}}
    ssl_context = object()
    monkeypatch.setattr(
        database,
        "get_ksqldb_httpx_kwargs",
        lambda: {"auth": ("runtime", "secret"), "verify": ssl_context},
    )
    httpx_get = Mock(return_value=response)
    monkeypatch.setattr(database.httpx, "get", httpx_get)

    assert database.is_ksqldb_available() is True
    httpx_get.assert_called_once_with(
        "http://localhost:8088/info",
        timeout=database.DEFAULT_CONNECTION_TIMEOUT,
        auth=("runtime", "secret"),
        verify=ssl_context,
    )
