import asyncio
import json
import os
import random
import re
import inspect
import ssl
from enum import Enum
from pathlib import Path
from typing import List
import uuid
import httpx
import pydantic
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import TopicAlreadyExistsError, KafkaError, for_code
from tksessentials import utils, global_logger
from tksessentials.constants import DEFAULT_ENCODING, DEFAULT_CONNECTION_TIMEOUT


logger = global_logger.setup_custom_logger("app")

_PROTECTED_ENVIRONMENTS = {"UAT", "PROD", "PRODUCTION"}
_KAFKA_SECURITY_PROTOCOLS = {"PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"}
_KAFKA_SASL_MECHANISMS = {
    "PLAIN",
    "SCRAM-SHA-256",
    "SCRAM-SHA-512",
}

class KSQLNotReadyError(Exception):
    pass

KSQL_NOT_READY_MESSAGE = "KSQL is not yet ready to serve requests."
KSQL_TABLE_EXISTS_MESSAGE = "A table with the same name already exists"
KSQL_STREAM_EXISTS_MESSAGE = "A stream with the same name already exists"

class KafkaKSqlDbEndPoint(str, Enum):
    KSQL = "ksql"
    KSQL_TERMINATE = "ksql/terminate"
    QUERY = "query"
    QUERY_STREAM = "query-stream"
    STATUS = "status"
    INFO = "info"
    CLUSTER_STATUS = "clusterStatus"
    IS_VALID_PROPERTY = "is_valid_property"


def deserialize_kafka_key(key_bytes: bytes | None) -> str | None:
    """Decode Kafka keys while preserving null keys."""
    if key_bytes is None:
        return None
    return key_bytes.decode(DEFAULT_ENCODING)


def deserialize_kafka_json_value(value_bytes: bytes | None):
    """Decode JSON Kafka values while preserving tombstones."""
    if value_bytes is None:
        return None
    return json.loads(value_bytes.decode(DEFAULT_ENCODING))

async def is_kafka_available() -> bool:
    """
    Check if the Kafka brokers are available.

    :param brokers: A string of Kafka brokers (e.g., 'localhost:9092')
    :return: True if available, False otherwise
    """
    producer = None
    try:
        producer = AIOKafkaProducer(**get_kafka_client_kwargs())
        await producer.start()
        return True
    except Exception as e:
        logger.error(f"Error checking Kafka availability: {e}")
        return False
    finally:
        if producer is not None:
            try:
                await producer.stop()
            except Exception:
                # Probe path: cleanup is best effort and should never mask availability state.
                pass


def _describe_check_name(check: object) -> str:
    return getattr(check, "__name__", check.__class__.__name__)


def _environment_name() -> str:
    environment = utils.get_environment()
    return environment.strip().upper() if isinstance(environment, str) else ""


def _is_dev_environment() -> bool:
    return _environment_name() == "DEV"


def _is_protected_environment() -> bool:
    return _environment_name() in _PROTECTED_ENVIRONMENTS


def _required_environment_value(name: str) -> str:
    value = os.getenv(name)
    if not isinstance(value, str) or not value.strip():
        environment = _environment_name() or "the current environment"
        raise ValueError(f"{name} must be set and non-empty in {environment}.")
    return value.strip()


def _optional_environment_value(name: str) -> str | None:
    value = os.getenv(name)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _resolve_required_file(name: str, required: bool) -> Path | None:
    raw_path = _optional_environment_value(name)
    if raw_path is None:
        if required:
            _required_environment_value(name)
        return None

    try:
        path = Path(raw_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"{name} does not reference a readable file: {raw_path}") from exc
    if not path.is_file():
        raise ValueError(f"{name} must reference a file: {raw_path}")
    return path


def _read_secret_file(name: str, required: bool) -> str | None:
    path = _resolve_required_file(name, required=required)
    if path is None:
        return None
    try:
        value = path.read_text(encoding=DEFAULT_ENCODING).rstrip("\r\n")
    except OSError as exc:
        raise ValueError(f"Unable to read the secret file referenced by {name}.") from exc
    if not value:
        raise ValueError(f"The secret file referenced by {name} is empty.")
    return value


def _ssl_context_from_ca_file(name: str, required: bool) -> ssl.SSLContext | None:
    path = _resolve_required_file(name, required=required)
    if path is None:
        return None
    try:
        return ssl.create_default_context(cafile=str(path))
    except (OSError, ssl.SSLError, ValueError) as exc:
        raise ValueError(f"Unable to load the CA certificate referenced by {name}.") from exc


def _strip_and_filter_broker_entries(values: List[str], default: List[str], require_port: bool = False) -> List[str]:
    if not isinstance(values, list):
        return default
    normalized: List[str] = []
    malformed: List[str] = []
    for value in values:
        if not isinstance(value, str):
            malformed.append(str(value))
            continue
        candidate = value.strip().rstrip("/")
        if not candidate:
            malformed.append(value)
            continue
        if require_port and ":" not in candidate:
            malformed.append(candidate)
            continue
        normalized.append(candidate)

    if malformed:
        logger.warning(f"Ignoring malformed endpoint values for brokers: {malformed}")

    return normalized or default


def _strip_and_filter_http_endpoints(values: List[str], default: List[str]) -> List[str]:
    if not isinstance(values, list):
        return default
    normalized: List[str] = []
    malformed: List[str] = []
    for value in values:
        if not isinstance(value, str):
            malformed.append(str(value))
            continue
        candidate = value.strip().rstrip("/")
        if not candidate:
            malformed.append(value)
            continue
        normalized.append(candidate)

    if malformed:
        logger.warning(f"Ignoring malformed endpoint values for ksqlDB nodes: {malformed}")

    return normalized or default


def _is_ksql_not_ready(response) -> bool:
    try:
        text = response.text
    except Exception:
        text = ""
    return isinstance(text, str) and KSQL_NOT_READY_MESSAGE in text


def _extract_ksql_resource_names(response, resource_key: str) -> set[str]:
    if getattr(response, "status_code", None) != 200:
        return set()
    try:
        payload = response.json()
    except Exception:
        return set()
    if not isinstance(payload, list) or not payload:
        return set()
    if not isinstance(payload[0], dict):
        return set()
    entries = payload[0].get(resource_key, [])
    if not isinstance(entries, list):
        return set()
    names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if isinstance(name, str):
            names.add(name.lower())
    return names


def _contains_marker(response, marker: str) -> bool:
    text = getattr(response, "text", "")
    return isinstance(text, str) and marker in text


def _extract_topic_errors(admin_response: object) -> list[dict]:
    if not isinstance(admin_response, dict):
        return []
    raw_errors = admin_response.get("topic_errors", [])
    return raw_errors if isinstance(raw_errors, list) else []


async def _flush_and_close_producer(producer) -> None:
    for method_name in ("flush", "stop"):
        method = getattr(producer, method_name, None)
        if method is None:
            continue
        try:
            await method()
        except Exception as exc:
            logger.debug(f"Failed during producer cleanup ({method_name}): {exc}")


def _is_retryable_sql_exception(exc: Exception) -> bool:
    # Preserve fail-fast behavior for clearly invalid request inputs.
    if isinstance(exc, (ValueError, TypeError, AttributeError)):
        return False
    return True


def _is_retryable_availability_exception(_check_name: str, exc: Exception) -> bool:
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        return False
    if isinstance(exc, (RuntimeError, ConnectionError, TimeoutError, OSError, KSQLNotReadyError)):
        return True
    if isinstance(exc, (ValueError, TypeError, AttributeError)):
        return False
    return True

def _normalize_broker_list(value: str | List[str] | None) -> List[str]:
    if value is None:
        return ["localhost:9092"]
    if isinstance(value, (list, tuple)):
        cleaned = [str(v).strip() for v in value if str(v).strip()]
        return _strip_and_filter_broker_entries(cleaned, ["localhost:9092"], require_port=True)
    if not isinstance(value, str):
        return ["localhost:9092"]
    raw = value.strip()
    if not raw or raw == "NODES_NOT_DEFINED":
        return ["localhost:9092"]
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return _strip_and_filter_broker_entries(parts, ["localhost:9092"], require_port=True)


def _strict_broker_list(value: str | List[str]) -> List[str]:
    raw_values = value if isinstance(value, (list, tuple)) else value.split(",")
    brokers: List[str] = []
    for raw_value in raw_values:
        if not isinstance(raw_value, str):
            raise ValueError("KAFKA_BROKER_STRING contains a non-string broker entry.")
        candidate = raw_value.strip().rstrip("/")
        host, separator, port = candidate.rpartition(":")
        if not candidate or not separator or not host or not port.isdigit():
            raise ValueError(
                "KAFKA_BROKER_STRING contains an invalid broker endpoint. "
                "Expected comma-separated host:port values."
            )
        port_number = int(port)
        if port_number < 1 or port_number > 65535:
            raise ValueError("KAFKA_BROKER_STRING contains an invalid broker port.")
        brokers.append(candidate)
    if not brokers:
        raise ValueError("KAFKA_BROKER_STRING must contain at least one broker endpoint.")
    return brokers


def _normalize_ksqldb_nodes(value: str | List[str] | None) -> List[str]:
    """Normalize ksqlDB node configuration without changing the public contract.

    Supported inputs remain additive:
    - a single URL string, e.g. "http://localhost:8088"
    - a comma-separated string of URLs
    - a list/tuple of URLs (mainly useful for tests or internal callers)
    """
    if value is None:
        return ["http://localhost:8088"]
    if isinstance(value, (list, tuple)):
        cleaned = [str(v).strip().rstrip("/") for v in value if str(v).strip()]
        return _strip_and_filter_http_endpoints(cleaned, ["http://localhost:8088"])
    if not isinstance(value, str):
        return ["http://localhost:8088"]
    raw = value.strip()
    if not raw or raw == "KSQLDB_NOT_DEFINED":
        return ["http://localhost:8088"]
    parts = [p.strip().rstrip("/") for p in raw.split(",") if p.strip()]
    return _strip_and_filter_http_endpoints(parts, ["http://localhost:8088"])


def _get_ksqldb_nodes() -> List[str]:
    if _is_protected_environment():
        raw_nodes = _required_environment_value("KSQLDB_STRING")
        nodes = _normalize_ksqldb_nodes(raw_nodes)
        if any(not node.lower().startswith("https://") for node in nodes):
            raise ValueError("KSQLDB_STRING must contain HTTPS endpoints in UAT/PROD.")
        return nodes
    return _normalize_ksqldb_nodes(os.getenv("KSQLDB_STRING", "KSQLDB_NOT_DEFINED"))


def get_kafka_cluster_brokers() -> List[str]:
    """Fetch the kafka broker array. This should return an array with nodes and ports.
    e.g. ['localhost:9092', 'localhost:9093']"""
    if _is_protected_environment():
        return _strict_broker_list(_required_environment_value("KAFKA_BROKER_STRING"))
    kafka_broker_value = os.getenv("KAFKA_BROKER_STRING", "NODES_NOT_DEFINED")
    return _normalize_broker_list(kafka_broker_value)


def get_kafka_client_kwargs(
    bootstrap_servers: str | List[str] | None = None,
) -> dict[str, object]:
    """Return one validated aiokafka connection contract for all client types.

    DEV keeps its zero-configuration localhost/PLAINTEXT behavior. UAT and PROD
    require SASL_SSL with SCRAM-SHA-512, a file-backed password, and a trusted CA.
    The optional bootstrap override exists for compatibility with snapshot readers;
    it never bypasses the environment's security requirements.
    """
    protected = _is_protected_environment()
    if bootstrap_servers is None:
        brokers = get_kafka_cluster_brokers()
    elif protected:
        brokers = _strict_broker_list(bootstrap_servers)
    else:
        brokers = _normalize_broker_list(bootstrap_servers)

    raw_protocol = _optional_environment_value("KAFKA_SECURITY_PROTOCOL")
    if protected and raw_protocol is None:
        raw_protocol = _required_environment_value("KAFKA_SECURITY_PROTOCOL")
    security_protocol = (raw_protocol or "PLAINTEXT").upper()
    if security_protocol not in _KAFKA_SECURITY_PROTOCOLS:
        raise ValueError(
            "KAFKA_SECURITY_PROTOCOL must be one of "
            f"{sorted(_KAFKA_SECURITY_PROTOCOLS)}."
        )
    if protected and security_protocol != "SASL_SSL":
        raise ValueError("KAFKA_SECURITY_PROTOCOL must be SASL_SSL in UAT/PROD.")

    client_kwargs: dict[str, object] = {
        "bootstrap_servers": ",".join(brokers),
        "security_protocol": security_protocol,
    }

    uses_sasl = security_protocol.startswith("SASL_")
    uses_tls = security_protocol in {"SSL", "SASL_SSL"}

    if uses_sasl:
        raw_mechanism = _required_environment_value("KAFKA_SASL_MECHANISM")
        sasl_mechanism = raw_mechanism.upper()
        if sasl_mechanism not in _KAFKA_SASL_MECHANISMS:
            raise ValueError(
                "KAFKA_SASL_MECHANISM must be one of "
                f"{sorted(_KAFKA_SASL_MECHANISMS)}."
            )
        if protected and sasl_mechanism != "SCRAM-SHA-512":
            raise ValueError("KAFKA_SASL_MECHANISM must be SCRAM-SHA-512 in UAT/PROD.")

        client_kwargs.update(
            {
                "sasl_mechanism": sasl_mechanism,
                "sasl_plain_username": _required_environment_value("KAFKA_SASL_USERNAME"),
                "sasl_plain_password": _read_secret_file(
                    "KAFKA_SASL_PASSWORD_FILE", required=True
                ),
            }
        )

    if uses_tls:
        ssl_context = _ssl_context_from_ca_file(
            "KAFKA_SSL_CA_FILE", required=protected
        )
        client_kwargs["ssl_context"] = ssl_context or ssl.create_default_context()
    elif _optional_environment_value("KAFKA_SSL_CA_FILE") is not None:
        raise ValueError(
            "KAFKA_SSL_CA_FILE is set but KAFKA_SECURITY_PROTOCOL does not enable TLS."
        )

    return client_kwargs


def get_ksqldb_httpx_kwargs() -> dict[str, object]:
    """Return the shared httpx authentication and TLS verification contract."""
    protected = _is_protected_environment()
    _get_ksqldb_nodes()

    username = _optional_environment_value("KSQLDB_USERNAME")
    password_file = _optional_environment_value("KSQLDB_PASSWORD_FILE")
    ca_file = _optional_environment_value("KSQLDB_CA_FILE")

    if protected:
        username = _required_environment_value("KSQLDB_USERNAME")
        password = _read_secret_file("KSQLDB_PASSWORD_FILE", required=True)
        ssl_context = _ssl_context_from_ca_file("KSQLDB_CA_FILE", required=True)
        return {"auth": (username, password), "verify": ssl_context}

    if bool(username) != bool(password_file):
        raise ValueError(
            "KSQLDB_USERNAME and KSQLDB_PASSWORD_FILE must either both be set or both be unset."
        )

    request_kwargs: dict[str, object] = {}
    if username:
        request_kwargs["auth"] = (
            username,
            _read_secret_file("KSQLDB_PASSWORD_FILE", required=True),
        )
    if ca_file:
        request_kwargs["verify"] = _ssl_context_from_ca_file(
            "KSQLDB_CA_FILE", required=True
        )
    return request_kwargs

def compose_consumer_id() -> str:
    """Do not mistaken the consumer_id for the consumer_group_name.
    The consumer group is unique for a group of consumers - since it is expected to be the kubernetes pod name.
    Where as the consumer_id - what this functin returns - is a globally unique identifier.
    As of now, regard the consumer_id and consumer_name the same."""
    return utils.get_pod_name()

def compose_consumer_group_name() -> str:
    """Do not mistaken the consumer_group_name for the consumer_id.
    The consumer group name - what this function returns - is unique for a group of consumers.
    Where as the consumer_id is a globally unique identifier.
    The consumer_group_name is composed of domain and application name."""
    return utils.get_application_identifier()

async def topic_exists(topic_name):
    consumer = AIOKafkaConsumer(**get_kafka_client_kwargs())
    await consumer.start()
    try:
        return topic_name in await consumer.topics()
    finally:
        await consumer.stop()


async def _topic_exists_with_retry(
    topic_name: str,
    attempts: int = 5,
    delay_s: float = 1.0,
) -> bool:
    """Recheck topic visibility briefly to absorb Kafka metadata propagation lag."""
    for attempt in range(attempts):
        if await topic_exists(topic_name):
            return True
        if attempt < attempts - 1:
            await asyncio.sleep(delay_s)
    return False

def compose_producer_id() -> str:
    """Creates a unique producer id: the pod_name."""
    return utils.get_pod_name()

async def get_default_kafka_producer(client_id: str | None = None) -> AIOKafkaProducer:
    """ Caution: Always stop/close this producer when done.
        This default producer is expecting you to send json data, which it will then automatically
        serialize/encode with UTF-8.
        The key must be a posix timestamp (int in python, BIGINT in Kafka).
        Feel free to create your own kafka producer, if these default values do no suite the use case.
    """
    if client_id is None:
        client_id = compose_producer_id()
    def get_value_serializer(v: any) -> bytes:
        if isinstance(v, pydantic.BaseModel):
            # Pydantic models need different deserialization
            return v.model_dump_json().encode(DEFAULT_ENCODING)
        else:
            return json.dumps(v).encode(DEFAULT_ENCODING)

    def get_key_serializer(k: str) -> bytes:
        return k.encode(DEFAULT_ENCODING)

    producer: AIOKafkaProducer = AIOKafkaProducer(
        **get_kafka_client_kwargs(),
        client_id=client_id,
        key_serializer=lambda k: get_key_serializer(k),
        value_serializer=lambda v: get_value_serializer(v))

    # start the producer for the client (it is often forgotten).
    await producer.start()
    return producer

async def get_default_kafka_consumer(
    topics: str,
    client: str | None = None,
    consumer_group: str = None,
    auto_commit: bool = True,
    auto_offset_reset="latest",
) -> AIOKafkaConsumer:
    """ Will return an async-capable consumer.
        However, you may create your own consumer with specific settings. This is only for convenience.
        The offset could be set to 'earliest'. Default is 'latest'.
        : param auto_commit (True): Set auto_commit to False to control the commits yourself.
    """
    if client is None:
        client = compose_consumer_id()

    # Create the Consumer instance
    consumer: AIOKafkaConsumer = AIOKafkaConsumer(topics,
                                                  **get_kafka_client_kwargs(),
                                                  client_id=client,
                                                  group_id=consumer_group,
                                                  key_deserializer=deserialize_kafka_key,
                                                  value_deserializer=deserialize_kafka_json_value,
                                                  auto_offset_reset=auto_offset_reset,
                                                  enable_auto_commit=auto_commit)
    await consumer.start()
    return consumer

def bytes_to_int_big_endian(key_bytes: bytes) -> int or None:
    """Converts 8 bytes in big-endian format back into an integer."""
    # Ensure that key_bytes is not None and is exactly 8 bytes
    if key_bytes is not None and len(key_bytes) == 8:
        return int.from_bytes(key_bytes, byteorder='big')
    else:
        # Handle cases where key_bytes is not 8 bytes as appropriate
        # This might include logging an error, raising an exception, or returning a default value
        return None  # Or your preferred way to handle this case

def is_ksqldb_available() -> bool:
    """
    Check if the ksqlDB server is available and running.

    :param ksql_url: The URL of the ksqlDB server (e.g., 'http://localhost:8088')
    :return: True if available, False otherwise
    """
    try:
        response = _ksqldb_get(get_ksqldb_url(KafkaKSqlDbEndPoint.INFO))
        if response.status_code == 200:
            info = response.json()
            if info.get('KsqlServerInfo', {}).get('serverStatus') == 'RUNNING':
                return True
        return False
    except Exception as e:
        logger.error(f"Error checking ksqlDB availability: {e}")
        return False

def get_ksqldb_url(kafka_ksqldb_endpoint_literal: KafkaKSqlDbEndPoint = KafkaKSqlDbEndPoint.KSQL) -> str:
    ksqldb_nodes = _get_ksqldb_nodes()
    if _is_dev_environment():
        base_url = random.choice(ksqldb_nodes)
        return f"{base_url}/{kafka_ksqldb_endpoint_literal.value}"
    else:
        base_url = ksqldb_nodes[0]
        return f"{base_url}/{kafka_ksqldb_endpoint_literal.value}"


def _ksqldb_get(url: str, timeout: float = DEFAULT_CONNECTION_TIMEOUT):
    return httpx.get(url, timeout=timeout, **get_ksqldb_httpx_kwargs())


def _ksqldb_post(
    url: str,
    payload: dict,
    timeout: float = DEFAULT_CONNECTION_TIMEOUT,
    headers: dict | None = None,
):
    return httpx.post(
        url,
        json=payload,
        headers=headers,
        timeout=timeout,
        **get_ksqldb_httpx_kwargs(),
    )

def table_or_view_exists(name: str, connection_time_out: float = DEFAULT_CONNECTION_TIMEOUT) -> bool:
    """Checks, if the provided table or queryable already exists."""
    ksql_url = get_ksqldb_url(KafkaKSqlDbEndPoint.KSQL)
    response = _ksqldb_post(
        ksql_url,
        {"ksql": "LIST TABLES;"},
        timeout=connection_time_out,
    )
    # logger.debug(f"Table Check Result: {response.status_code}: {response.text}")
    # Check if the request was successful
    if response.status_code == 200:
        tables = _extract_ksql_resource_names(response, "tables")
        if str(name).lower() in tables:
            logger.debug(f"Table {name} exists.")
            return True
    elif _is_ksql_not_ready(response):
        logger.warning(f"KSQL is not ready to create the table {name}. Retrying...")
        raise KSQLNotReadyError("KSQL is not yet ready to serve requests.")
    else:
        logger.debug(f"Table {name} does not exists.")
        raise Exception(f'Failed to test if table or view exists in Kafka: {response.status_code}')

    return False

async def prepare_sql_statement(sql_statement: str) -> str:
    """If the DDL (sql_statement) one submits to create a table is a CTAS, then we:
    1) we parse the query for "KAFKA_TOPIC"
    2) check if the topic exists.
    3) if it exists, remove the PARTITIONS config of the sql_statement entirly to avoid conflicts.
    4) if it does not exists, we keep the sql_statement unmodified.
    """
    kafka_topic_match = re.search(r"KAFKA_TOPIC\s*=\s*'([^']+)'", sql_statement, re.IGNORECASE)
    if kafka_topic_match:
        partitions_match = re.search(r"PARTITIONS\s*=\s*\d+", sql_statement, re.IGNORECASE)
        kafka_topic = kafka_topic_match.group(1)
        if await _topic_exists_with_retry(kafka_topic):
            logger.info(f"Kafka topic {kafka_topic} exists.")
            if partitions_match:
                sql_statement = re.sub(r",?\s*PARTITIONS\s*=\s*\d+", "", sql_statement)
                logger.debug(f"PARTITIONS argument has been removed from the SQL statement, since the topic already exists. {sql_statement}")
            return sql_statement
        else:
            logger.info(f"Kafka topic {kafka_topic} does not exist. Setting PARTITIONS to 6 if not specified.")
            if not partitions_match:
                sql_statement = re.sub(r"\);", ", PARTITIONS=6);", sql_statement)
            return sql_statement
    return sql_statement

def clean_sql_statement(sql_statement: str) -> str:
    """Cleans the SQL statement by removing unnecessary spacing, newlines, and tabs."""
    return ' '.join(sql_statement.split())

async def create_table(sql_statement: str, table_name: str):
    """The invocation of this function will retry endlessly if the httpx.RemoteProtocolError or httpx.ConnectError occures. This implies, that the cluster is not yet ready and thus we need to retry.
    For all other exceptions, we retry for 60 seconds (every 5 seconds).
    """
    logger.info(f"Attempting to create table {table_name} with SQL statement {sql_statement}.")
    sql_statement = clean_sql_statement(sql_statement)
    logger.info(f"Cleaned SQL statement: {sql_statement}")
    sql_statement = await prepare_sql_statement(sql_statement)
    logger.info(f"Prepared SQL statement: {sql_statement}")
    headers = {"Content-Type": "application/json"}
    response = _ksqldb_post(
        get_ksqldb_url(KafkaKSqlDbEndPoint.KSQL),
        {"ksql": sql_statement},
        headers=headers,
        timeout=30,
    )

    if response.status_code == 200:
        logger.info(f"Successfully created table {table_name}.")
    else:
        if _contains_marker(response, KSQL_TABLE_EXISTS_MESSAGE):
            logger.info(f"Table {table_name} already exists. Skipping creation.")
            return
        elif _is_ksql_not_ready(response):
            logger.warning(f"KSQL is not ready to create the table {table_name}. Retrying...")
            raise KSQLNotReadyError("KSQL is not yet ready to serve requests.")
        else:
            error_msg = f"Failed to create table {table_name}: {response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)

    # Wait until the table is created
    max_wait_time = 60  # seconds
    poll_interval = 5  # seconds
    elapsed_time = 0

    while elapsed_time < max_wait_time:
        if table_or_view_exists(table_name):
            logger.info(f"Table {table_name} is now available.")
            return
        else:
            logger.debug(f"Table {table_name} is not yet available. Waiting...")
            await asyncio.sleep(poll_interval)
            elapsed_time += poll_interval

    logger.error(f"Timed out waiting for table {table_name} to be created.")
    raise TimeoutError(f"Timed out waiting for table {table_name} to be created.")

def stream_exists(name: str, connection_time_out: float = 60.0) -> bool:
    """Checks, if the provided table or queryable already exists."""
    ksql_url = get_ksqldb_url(KafkaKSqlDbEndPoint.KSQL)
    response = _ksqldb_post(
        ksql_url,
        {"ksql": "LIST STREAMS;"},
        timeout=connection_time_out,
    )
    # logger.debug(f"Stream Check Result: {response}")
    # logger.info(f"{response.status_code}: {response.text}")
    # Check if the request was successful
    if response.status_code == 200:
        streams = _extract_ksql_resource_names(response, "streams")
        if str(name).lower() in streams:
            logger.debug(f"Stream {name} exists.")
            return True
    elif _is_ksql_not_ready(response):
        logger.warning(f"KSQL is not ready to create the stream {name}. Retrying...")
        raise KSQLNotReadyError("KSQL is not yet ready to serve requests.")
    else:
        logger.debug(f"Stream {name} does not exists.")
        raise Exception(f'Failed to test if stream exists in Kafka: {response.status_code}')

    return False

async def create_stream(sql_statement: str, stream_name: str):
    """The invocation of this function will retry endlessly if the httpx.RemoteProtocolError or httpx.ConnectError occures. This implies, that the cluster is not yet ready and thus we need to retry.
    For all other exceptions, we retry for 60 seconds (every 5 seconds).
    """
    logger.info(f"Attempting to create stream {stream_name} with SQL statement {sql_statement}.")
    sql_statement = clean_sql_statement(sql_statement)
    logger.info(f"Cleaned SQL statement: {sql_statement}")
    sql_statement = await prepare_sql_statement(sql_statement)
    logger.info(f"Prepared SQL statement: {sql_statement}")
    headers = {"Content-Type": "application/json"}
    response = _ksqldb_post(
        get_ksqldb_url(KafkaKSqlDbEndPoint.KSQL),
        {"ksql": sql_statement},
        headers=headers,
        timeout=30,
    )

    if response.status_code == 200:
        logger.info(f"Successfully created stream {stream_name}.")
    else:
        if _contains_marker(response, KSQL_STREAM_EXISTS_MESSAGE):
            logger.info(f"Stream {stream_name} already exists. Skipping creation.")
            return
        elif _is_ksql_not_ready(response):
            logger.warning(f"KSQL is not ready to create the stream {stream_name}. Retrying...")
            raise KSQLNotReadyError("KSQL is not yet ready to serve requests.")
        else:
            error_msg = f"Failed to create stream {stream_name}: {response.text}"
            logger.error(error_msg)
            raise Exception(error_msg)

    # Wait until the table is created
    max_wait_time = 60  # seconds
    poll_interval = 5  # seconds
    elapsed_time = 0

    while elapsed_time < max_wait_time:
        if stream_exists(stream_name):
            logger.info(f"Stream {stream_name} is now available.")
            return
        else:
            logger.debug(f"Stream {stream_name} is not yet available. Waiting...")
            await asyncio.sleep(poll_interval)
            elapsed_time += poll_interval

    logger.error(f"Timed out waiting for stream {stream_name} to be created.")
    raise TimeoutError(f"Timed out waiting for stream {stream_name} to be created.")

async def execute_sql(sql: str, connection_time_out: float = DEFAULT_CONNECTION_TIMEOUT):
    """Executes the provided sql command. To create tables, use the create_table function instead."""

    ksql_url = get_ksqldb_url(KafkaKSqlDbEndPoint.KSQL)
    response = _ksqldb_post(
        ksql_url,
        {"ksql": sql},
        timeout=connection_time_out,
    )

    # Check if the request was successful
    if response.status_code == 200:
        logger.info(f"The provided SQL statement executed successfully. SQL: {sql}")
    else:
        raise Exception(f"Failed to execute SQL statement: {response.status_code}. SQL: {sql}")

async def produce_message(topic_name: str, key: str, value: any) -> None:
    """Will send the provided message to the specified Kafka topic and ends the producer when accomplished.."""
    kp = await get_default_kafka_producer()
    try:
        await kp.send_and_wait(topic=topic_name, key=key, value=value)
    except KafkaError as ke:
        error_message = f"""An error occurred when trying to send a message of type {type(value)} to the database.
                        Error message: {ke}"""
        logger.error(error_message)
        raise Exception(error_message)
    except Exception as ex:
        error_message = f"""A general error occurred when trying to send a message of type {type(value)}
                        to the database. Error message: {ex}"""
        logger.error(error_message)
        raise Exception(error_message)
    finally:
        # Wait for all pending messages to be delivered or expire.
        await _flush_and_close_producer(kp)

async def check_availability_with_retry(check_functions, max_wait_time=None, poll_interval=5):
    """Checks the availability of services with retry logic.

    Args:
        check_functions (list): List of functions to check service availability.
                                The functions can be a mix of async and sync functions.
        max_wait_time (int or None): Maximum wait time in seconds. If None, wait indefinitely.
        poll_interval (int): Poll interval in seconds.

    Raises:
        TimeoutError: If services are not available within the max wait time.
    """
    elapsed_time = 0

    while max_wait_time is None or elapsed_time < max_wait_time:
        checks = []
        for check in check_functions or []:
            check_name = _describe_check_name(check)
            try:
                if inspect.iscoroutinefunction(check):
                    # If the function is async, await it
                    result = await check()
                else:
                    # If the function is sync, call it directly
                    result = check()

                # Log the result of each check
                if check_name == 'is_kafka_available':
                    if result:
                        logger.info("Kafka is available.")
                    else:
                        logger.info("Kafka is not available.")
                elif check_name == 'is_ksqldb_available':
                    if result:
                        logger.info("ksqlDB is available.")
                    else:
                        logger.info("ksqlDB is not available.")
                else:
                    logger.debug(f"Check '{check_name}' result: {result}")

                checks.append(bool(result))
            except Exception as e:
                if not _is_retryable_availability_exception(check_name, e):
                    raise
                if check_name == 'is_kafka_available':
                    logger.error(f"Error checking Kafka availability: {e}")
                    logger.info("Kafka is not available.")
                elif check_name == 'is_ksqldb_available':
                    logger.error(f"Error checking ksqlDB availability: {e}")
                    logger.info("ksqlDB is not available.")
                else:
                    logger.error(f"Error checking {check_name}: {e}")
                checks.append(False)

        if all(checks):
            logger.info("All services are available. Proceeding...")
            return True
        else:
            logger.info("One or more services are not available. Retrying...")
            await asyncio.sleep(poll_interval)
            elapsed_time += poll_interval

    logger.error("Timed out waiting for services to be available.")
    raise TimeoutError("Timed out waiting for services to be available.")

async def execute_with_retries(sql_task, retries=None, delay=20):
    attempt = 0
    while retries is None or attempt < retries:
        try:
            await sql_task()  # Execute the task directly
            return
        except Exception as e:
            attempt += 1
            if not _is_retryable_sql_exception(e):
                raise
            logger.info(f"Failed to execute SQL statement (attempt {attempt}): {e}")
            if retries is None or attempt < retries:
                logger.info(f"Retrying in {delay} seconds...")
                await asyncio.sleep(delay)
            else:
                break  # Exceeded max retries

    raise Exception(f"Failed to execute SQL after {attempt} attempts: {sql_task}")

def _normalize_cleanup_policy(cleanup_policy: str | List[str] | None, compacted: bool) -> str:
    """Return a valid Kafka cleanup.policy string while preserving backward compatibility.

    Rules:
    - cleanup_policy=None -> derive from compacted (compact/delete)
    - cleanup_policy=str/list -> normalize and deduplicate, preserving order
    - if compacted=True and compact is not present, append compact
    """
    if cleanup_policy is None:
        policies = ["compact"] if compacted else ["delete"]
    else:
        raw_values: List[str]
        if isinstance(cleanup_policy, str):
            raw_values = cleanup_policy.split(",")
        else:
            raw_values = [str(value) for value in cleanup_policy]

        policies = []
        for value in raw_values:
            normalized = value.strip().lower()
            if normalized and normalized not in policies:
                policies.append(normalized)

        if not policies:
            policies = ["compact"] if compacted else ["delete"]

        invalid = [policy for policy in policies if policy not in {"delete", "compact"}]
        if invalid:
            raise ValueError(
                f"Invalid cleanup policy value(s): {invalid}. Allowed values: 'delete', 'compact'."
            )

        if compacted and "compact" not in policies:
            policies.append("compact")

    return ",".join(policies)


async def create_topic(
    topic_name: str,
    partitions: int = 6,
    replication_factor: int = 2,
    compacted: bool = False,
    cleanup_policy: str | List[str] | None = None,
):
    """Create a Kafka topic if it does not exist, using aiokafka’s async admin API."""
    admin = AIOKafkaAdminClient(**get_kafka_client_kwargs())
    # 1. Bootstrap metadata (must do this before calling create_topics)
    await admin.start()  # :contentReference[oaicite:2]{index=2}
    try:
        topic_configs = {
            "retention.ms": "-1",
            "retention.bytes": "-1",
            "cleanup.policy": _normalize_cleanup_policy(cleanup_policy, compacted),
        }
        # 2. Define topic spec
        new_topic = NewTopic(
            name=topic_name,
            num_partitions=partitions,
            replication_factor=replication_factor,
            topic_configs=topic_configs,
        )
        # 3. Create it and validate result codes
        response = await admin.create_topics(new_topics=[new_topic], validate_only=False)
        try:
            response_to_object = response.to_object() if callable(getattr(response, "to_object", None)) else None
        except Exception:
            response_to_object = None

        topic_errors = _extract_topic_errors(response_to_object)
        if topic_errors:
            for entry in topic_errors:
                if not isinstance(entry, dict):
                    continue
                if entry.get("topic") != topic_name:
                    continue
                error_code = entry.get("error_code", 0)
                if error_code != 0:
                    error_cls = for_code(error_code)
                    if error_cls is TopicAlreadyExistsError:
                        logger.info(f"Topic '{topic_name}' already exists.")
                        return
                    error_message = entry.get("error_message")
                    message = f"Failed to create topic '{topic_name}' (error_code={error_code})"
                    if error_message:
                        message = f"{message}: {error_message}"
                    raise error_cls(message)
                break
        logger.info(f"Topic '{topic_name}' created successfully.")
        # Wait until the broker reports partitions for the topic
        max_wait = 30
        waited = 0
        poll = 1
        describe_error_count = 0
        max_describe_error_logs = 3
        while waited < max_wait:
            try:
                obj = await admin.describe_topics([topic_name])
                if obj and isinstance(obj, list):
                    for t in obj:
                        if not isinstance(t, dict):
                            continue
                        if t.get("topic") == topic_name and t.get("partitions"):
                            return
            except Exception as exc:
                # ignore transient errors while waiting for metadata
                if describe_error_count < max_describe_error_logs:
                    describe_error_count += 1
                    logger.debug(
                        f"Transient error while waiting for metadata for topic '{topic_name}' (attempt {describe_error_count}): {exc}"
                    )
            await asyncio.sleep(poll)
            waited += poll
    except TopicAlreadyExistsError:
        logger.info(f"Topic '{topic_name}' already exists.")
    except KafkaError as e:
        # any other Kafka‐level error
        logger.error(f"Failed to create topic '{topic_name}': {e}")
        raise
    finally:
        # 4. Clean up the admin client
        await admin.close()

async def read_compacted_state_snapshot(
    topic: str,
    bootstrap_servers: str | list[str],
    logger,
    timeout_s: float = 10.0,
    max_empty_polls: int = 3,
) -> dict[str, dict]:
    """
    Reads a compacted topic from beginning to the current end offsets and returns latest value per key.

    - key: market (string)
    - value: dict (your message) OR None (tombstone)
    """
    # IMPORTANT: use a unique group id so we don't reuse committed offsets.
    group_id = f"snapshot-{uuid.uuid4()}"

    consumer = AIOKafkaConsumer(
        topic,
        **get_kafka_client_kwargs(bootstrap_servers),
        group_id=group_id,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        key_deserializer=deserialize_kafka_key,
        value_deserializer=deserialize_kafka_json_value,
    )

    latest: dict[str, dict | None] = {}

    try:
        await consumer.start()

        # Wait for partition assignment
        # (poll once to trigger assignment)
        await consumer.getmany(timeout_ms=1)

        partitions = consumer.assignment()
        if not partitions:
            # Sometimes assignment needs a moment
            await asyncio.sleep(0.2)
            await consumer.getmany(timeout_ms=1)
            partitions = consumer.assignment()

        if not partitions:
            logger.warning(f"No partitions assigned for topic {topic}. Returning empty snapshot.")
            return {}

        # Force start at beginning for all assigned partitions
        await consumer.seek_to_beginning(*partitions)

        # Capture end offsets (the stopping point)
        end_offsets = await consumer.end_offsets(list(partitions))

        empty_polls = 0
        while True:
            batch = await consumer.getmany(timeout_ms=int(timeout_s * 1000), max_records=5000)

            got_any = False
            for tp, messages in batch.items():
                if not messages:
                    continue
                got_any = True
                for msg in messages:
                    k = msg.key
                    v = msg.value
                    if k is None:
                        continue  # skip malformed
                    latest[k] = v  # v can be None (tombstone)

            if not got_any:
                empty_polls += 1
            else:
                empty_polls = 0

            # Check if we've reached (or passed) end offsets for all partitions
            done = True
            for tp in partitions:
                pos = await consumer.position(tp)
                if pos < end_offsets[tp]:
                    done = False
                    break

            if done:
                break

            # safety valve: if topic is idle and we keep polling nothing, stop
            if empty_polls >= max_empty_polls:
                break

        # Return only non-tombstoned entries
        return {k: v for k, v in latest.items() if v is not None}

    except KafkaError as e:
        logger.error(f"Error snapshotting topic {topic}: {e}")
        return {}
    finally:
        await consumer.stop()
