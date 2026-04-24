import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pydantic
import pytest
from aiokafka.errors import KafkaError, TopicAlreadyExistsError

from tksessentials import database
from tksessentials.database import KafkaKSqlDbEndPoint, KSQLNotReadyError


class _Response:
    def __init__(self, status_code=200, text="", payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload if payload is not None else []

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_is_kafka_available_success(monkeypatch):
    class FakeProducer:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.started = False
            self.stopped = False

        async def start(self):
            self.started = True

        async def stop(self):
            self.stopped = True

    monkeypatch.setattr(database, "get_kafka_cluster_brokers", lambda: ["broker-a:9092"])
    monkeypatch.setattr(database, "AIOKafkaProducer", FakeProducer)

    assert await database.is_kafka_available() is True


@pytest.mark.asyncio
async def test_is_kafka_available_failure(monkeypatch):
    class FailingProducer:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def start(self):
            raise RuntimeError("boom")

        async def stop(self):
            return None

    monkeypatch.setattr(database, "get_kafka_cluster_brokers", lambda: ["broker-a:9092"])
    monkeypatch.setattr(database, "AIOKafkaProducer", FailingProducer)

    assert await database.is_kafka_available() is False


def test_compose_consumer_group_name(monkeypatch):
    monkeypatch.setattr(database.utils, "get_application_identifier", lambda: "domain-service")
    assert database.compose_consumer_group_name() == "domain-service"


@pytest.mark.asyncio
async def test_topic_exists_starts_and_stops_consumer(monkeypatch):
    class FakeConsumer:
        def __init__(self, **kwargs):
            self.started = False
            self.stopped = False

        async def start(self):
            self.started = True

        async def stop(self):
            self.stopped = True

        async def topics(self):
            return {"topic_a", "topic_b"}

    consumer = FakeConsumer()
    monkeypatch.setattr(database, "AIOKafkaConsumer", lambda **kwargs: consumer)
    monkeypatch.setattr(database, "get_kafka_cluster_brokers", lambda: ["localhost:9092"])

    assert await database.topic_exists("topic_a") is True
    assert consumer.started is True
    assert consumer.stopped is True


@pytest.mark.asyncio
async def test_topic_exists_with_retry_eventual_success(monkeypatch):
    attempts = iter([False, False, True])
    sleep = AsyncMock(return_value=None)

    async def fake_topic_exists(topic_name):
        return next(attempts)

    monkeypatch.setattr(database, "topic_exists", fake_topic_exists)
    monkeypatch.setattr(database.asyncio, "sleep", sleep)

    assert await database._topic_exists_with_retry("topic_a", attempts=3, delay_s=0.1) is True
    assert sleep.await_count == 2


@pytest.mark.asyncio
async def test_topic_exists_with_retry_returns_false_after_exhaustion(monkeypatch):
    sleep = AsyncMock(return_value=None)

    async def fake_topic_exists(topic_name):
        return False

    monkeypatch.setattr(database, "topic_exists", fake_topic_exists)
    monkeypatch.setattr(database.asyncio, "sleep", sleep)

    assert await database._topic_exists_with_retry("topic_a", attempts=3, delay_s=0.1) is False
    assert sleep.await_count == 2


@pytest.mark.asyncio
async def test_get_default_kafka_producer_serializers(monkeypatch):
    class SampleModel(pydantic.BaseModel):
        name: str
        value: int

    class FakeProducer:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.started = False

        async def start(self):
            self.started = True

    monkeypatch.setattr(database, "get_kafka_cluster_brokers", lambda: ["broker1:9092", "broker2:9092"])
    monkeypatch.setattr(database, "AIOKafkaProducer", FakeProducer)

    producer = await database.get_default_kafka_producer(client_id="client-1")

    assert producer.started is True
    assert producer.kwargs["bootstrap_servers"] == "broker1:9092,broker2:9092"
    assert producer.kwargs["client_id"] == "client-1"
    assert producer.kwargs["key_serializer"]("abc") == b"abc"
    assert json.loads(producer.kwargs["value_serializer"](SampleModel(name="x", value=1)).decode("utf-8")) == {
        "name": "x",
        "value": 1,
    }
    assert json.loads(producer.kwargs["value_serializer"]({"a": 1}).decode("utf-8")) == {"a": 1}


@pytest.mark.asyncio
async def test_get_default_kafka_consumer_deserializers(monkeypatch):
    class FakeConsumer:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.started = False

        async def start(self):
            self.started = True

    monkeypatch.setattr(database, "get_kafka_cluster_brokers", lambda: ["broker1:9092"])
    monkeypatch.setattr(database, "AIOKafkaConsumer", FakeConsumer)

    consumer = await database.get_default_kafka_consumer(
        "topic_x",
        client="client-x",
        consumer_group="group-x",
        auto_commit=False,
        auto_offset_reset="earliest",
    )

    assert consumer.args[0] == "topic_x"
    assert consumer.kwargs["bootstrap_servers"] == "broker1:9092"
    assert consumer.kwargs["client_id"] == "client-x"
    assert consumer.kwargs["group_id"] == "group-x"
    assert consumer.kwargs["enable_auto_commit"] is False
    assert consumer.kwargs["auto_offset_reset"] == "earliest"
    assert consumer.kwargs["key_deserializer"](b"key-1") == "key-1"
    assert consumer.kwargs["key_deserializer"](None) is None
    assert consumer.kwargs["value_deserializer"](b'{"ok": true}') == {"ok": True}
    assert consumer.kwargs["value_deserializer"](None) is None
    assert consumer.started is True


def test_bytes_to_int_big_endian():
    assert database.bytes_to_int_big_endian((123).to_bytes(8, byteorder="big")) == 123
    assert database.bytes_to_int_big_endian(None) is None
    assert database.bytes_to_int_big_endian(b"\x01\x02") is None


def test_get_ksqldb_url_non_dev_branch(monkeypatch):
    monkeypatch.setattr(database.utils, "get_environment", lambda: "PROD")
    monkeypatch.setenv("KSQLDB_STRING", "http://ksql.prod:8088/")

    url = database.get_ksqldb_url(KafkaKSqlDbEndPoint.INFO)
    assert url == "http://ksql.prod:8088/info"


def test_get_ksqldb_url_dev_branch_uses_normalized_nodes(monkeypatch):
    monkeypatch.setattr(database.utils, "get_environment", lambda: "DEV")
    monkeypatch.setenv("KSQLDB_STRING", "http://ksql.dev:8088/")
    monkeypatch.setattr(database.random, "choice", lambda values: values[0])

    url = database.get_ksqldb_url(KafkaKSqlDbEndPoint.INFO)
    assert url == "http://ksql.dev:8088/info"


def test_get_ksqldb_url_dev_branch_supports_comma_separated_nodes(monkeypatch):
    monkeypatch.setattr(database.utils, "get_environment", lambda: "DEV")
    monkeypatch.setenv(
        "KSQLDB_STRING",
        "http://ksql-a.dev:8088/,http://ksql-b.dev:8088/",
    )
    monkeypatch.setattr(database.random, "choice", lambda values: values[-1])

    url = database.get_ksqldb_url(KafkaKSqlDbEndPoint.INFO)
    assert url == "http://ksql-b.dev:8088/info"


def test_get_ksqldb_url_non_dev_branch_uses_first_node_from_comma_separated_config(monkeypatch):
    monkeypatch.setattr(database.utils, "get_environment", lambda: "PROD")
    monkeypatch.setenv(
        "KSQLDB_STRING",
        "http://ksql-a.prod:8088/,http://ksql-b.prod:8088/",
    )

    url = database.get_ksqldb_url(KafkaKSqlDbEndPoint.INFO)
    assert url == "http://ksql-a.prod:8088/info"


def test_get_kafka_cluster_brokers_non_dev_handles_non_string_environment(monkeypatch):
    monkeypatch.setattr(database.utils, "get_environment", lambda: None)
    monkeypatch.delenv("KAFKA_BROKER_STRING", raising=False)
    assert database.get_kafka_cluster_brokers() == ["localhost:9092"]


def test_get_kafka_cluster_brokers_filters_missing_ports():
    assert database._normalize_broker_list(["bad-node", "localhost:9092"]) == ["localhost:9092"]


def test_get_ksqldb_url_non_dev_handles_non_string_environment(monkeypatch):
    monkeypatch.setattr(database.utils, "get_environment", lambda: None)
    monkeypatch.setenv("KSQLDB_STRING", "http://ksql.prod:8088/")
    assert database.get_ksqldb_url(KafkaKSqlDbEndPoint.INFO) == "http://ksql.prod:8088/info"


def test_get_ksqldb_url_uses_first_default_when_nodes_invalid(monkeypatch):
    monkeypatch.setattr(database.utils, "get_environment", lambda: "PROD")
    monkeypatch.setenv("KSQLDB_STRING", "  ,   ")
    assert database.get_ksqldb_url(KafkaKSqlDbEndPoint.INFO) == "http://localhost:8088/info"


def test_table_or_view_exists_ready_error():
    response = _Response(status_code=503, text="KSQL is not yet ready to serve requests.")
    with patch("tksessentials.database.httpx.post", return_value=response):
        with pytest.raises(KSQLNotReadyError):
            database.table_or_view_exists("ORDERS")


def test_table_or_view_exists_generic_error():
    response = _Response(status_code=500, text="internal error")
    with patch("tksessentials.database.httpx.post", return_value=response):
        with pytest.raises(Exception, match="Failed to test if table or view exists in Kafka: 500"):
            database.table_or_view_exists("ORDERS")


@pytest.mark.asyncio
async def test_prepare_sql_statement_passthrough_without_kafka_topic():
    sql = "SELECT * FROM table_without_with_clause;"
    assert await database.prepare_sql_statement(sql) == sql


@pytest.mark.asyncio
async def test_create_table_success_waits_until_available():
    response = _Response(status_code=200)
    with patch("tksessentials.database.clean_sql_statement", return_value="SQL"), patch(
        "tksessentials.database.prepare_sql_statement", AsyncMock(return_value="SQL")
    ), patch("tksessentials.database.get_ksqldb_url", return_value="http://ksql/ksql"), patch(
        "tksessentials.database.httpx.post", return_value=response
    ), patch(
        "tksessentials.database.table_or_view_exists", side_effect=[False, True]
    ), patch(
        "tksessentials.database.asyncio.sleep", AsyncMock(return_value=None)
    ):
        await database.create_table("RAW SQL", "orders_table")


@pytest.mark.asyncio
async def test_create_table_already_exists_short_circuits():
    response = _Response(status_code=400, text="A table with the same name already exists")
    with patch("tksessentials.database.clean_sql_statement", return_value="SQL"), patch(
        "tksessentials.database.prepare_sql_statement", AsyncMock(return_value="SQL")
    ), patch("tksessentials.database.get_ksqldb_url", return_value="http://ksql/ksql"), patch(
        "tksessentials.database.httpx.post", return_value=response
    ):
        await database.create_table("RAW SQL", "orders_table")


@pytest.mark.asyncio
async def test_create_table_not_ready_raises():
    response = _Response(status_code=503, text="KSQL is not yet ready to serve requests.")
    with patch("tksessentials.database.clean_sql_statement", return_value="SQL"), patch(
        "tksessentials.database.prepare_sql_statement", AsyncMock(return_value="SQL")
    ), patch("tksessentials.database.get_ksqldb_url", return_value="http://ksql/ksql"), patch(
        "tksessentials.database.httpx.post", return_value=response
    ):
        with pytest.raises(KSQLNotReadyError):
            await database.create_table("RAW SQL", "orders_table")


@pytest.mark.asyncio
async def test_create_table_generic_error_raises():
    response = _Response(status_code=500, text="explode")
    with patch("tksessentials.database.clean_sql_statement", return_value="SQL"), patch(
        "tksessentials.database.prepare_sql_statement", AsyncMock(return_value="SQL")
    ), patch("tksessentials.database.get_ksqldb_url", return_value="http://ksql/ksql"), patch(
        "tksessentials.database.httpx.post", return_value=response
    ):
        with pytest.raises(Exception, match="Failed to create table orders_table: explode"):
            await database.create_table("RAW SQL", "orders_table")


@pytest.mark.asyncio
async def test_create_table_timeout():
    response = _Response(status_code=200)
    with patch("tksessentials.database.clean_sql_statement", return_value="SQL"), patch(
        "tksessentials.database.prepare_sql_statement", AsyncMock(return_value="SQL")
    ), patch("tksessentials.database.get_ksqldb_url", return_value="http://ksql/ksql"), patch(
        "tksessentials.database.httpx.post", return_value=response
    ), patch(
        "tksessentials.database.table_or_view_exists", return_value=False
    ), patch(
        "tksessentials.database.asyncio.sleep", AsyncMock(return_value=None)
    ):
        with pytest.raises(TimeoutError):
            await database.create_table("RAW SQL", "orders_table")


def test_stream_exists_ready_error():
    response = _Response(status_code=503, text="KSQL is not yet ready to serve requests.")
    with patch("tksessentials.database.httpx.post", return_value=response):
        with pytest.raises(KSQLNotReadyError):
            database.stream_exists("orders_stream")


def test_stream_exists_generic_error():
    response = _Response(status_code=500, text="internal error")
    with patch("tksessentials.database.httpx.post", return_value=response):
        with pytest.raises(Exception, match="Failed to test if stream exists in Kafka: 500"):
            database.stream_exists("orders_stream")


@pytest.mark.asyncio
async def test_create_stream_success_waits_until_available():
    response = _Response(status_code=200)
    with patch("tksessentials.database.clean_sql_statement", return_value="SQL"), patch(
        "tksessentials.database.prepare_sql_statement", AsyncMock(return_value="SQL")
    ), patch("tksessentials.database.get_ksqldb_url", return_value="http://ksql/ksql"), patch(
        "tksessentials.database.httpx.post", return_value=response
    ), patch(
        "tksessentials.database.stream_exists", side_effect=[False, True]
    ), patch(
        "tksessentials.database.asyncio.sleep", AsyncMock(return_value=None)
    ):
        await database.create_stream("RAW SQL", "orders_stream")


@pytest.mark.asyncio
async def test_create_stream_not_ready_raises():
    response = _Response(status_code=503, text="KSQL is not yet ready to serve requests.")
    with patch("tksessentials.database.clean_sql_statement", return_value="SQL"), patch(
        "tksessentials.database.prepare_sql_statement", AsyncMock(return_value="SQL")
    ), patch("tksessentials.database.get_ksqldb_url", return_value="http://ksql/ksql"), patch(
        "tksessentials.database.httpx.post", return_value=response
    ):
        with pytest.raises(KSQLNotReadyError):
            await database.create_stream("RAW SQL", "orders_stream")


@pytest.mark.asyncio
async def test_create_stream_generic_error_raises():
    response = _Response(status_code=500, text="explode")
    with patch("tksessentials.database.clean_sql_statement", return_value="SQL"), patch(
        "tksessentials.database.prepare_sql_statement", AsyncMock(return_value="SQL")
    ), patch("tksessentials.database.get_ksqldb_url", return_value="http://ksql/ksql"), patch(
        "tksessentials.database.httpx.post", return_value=response
    ):
        with pytest.raises(Exception, match="Failed to create stream orders_stream: explode"):
            await database.create_stream("RAW SQL", "orders_stream")


@pytest.mark.asyncio
async def test_create_stream_timeout():
    response = _Response(status_code=200)
    with patch("tksessentials.database.clean_sql_statement", return_value="SQL"), patch(
        "tksessentials.database.prepare_sql_statement", AsyncMock(return_value="SQL")
    ), patch("tksessentials.database.get_ksqldb_url", return_value="http://ksql/ksql"), patch(
        "tksessentials.database.httpx.post", return_value=response
    ), patch(
        "tksessentials.database.stream_exists", return_value=False
    ), patch(
        "tksessentials.database.asyncio.sleep", AsyncMock(return_value=None)
    ):
        with pytest.raises(TimeoutError):
            await database.create_stream("RAW SQL", "orders_stream")


@pytest.mark.asyncio
async def test_execute_sql_success():
    response = _Response(status_code=200)
    with patch("tksessentials.database.get_ksqldb_url", return_value="http://ksql/ksql"), patch(
        "tksessentials.database.httpx.post", return_value=response
    ):
        await database.execute_sql("SELECT 1;")


@pytest.mark.asyncio
async def test_execute_sql_failure_raises():
    response = _Response(status_code=400, text="bad sql")
    with patch("tksessentials.database.get_ksqldb_url", return_value="http://ksql/ksql"), patch(
        "tksessentials.database.httpx.post", return_value=response
    ):
        with pytest.raises(Exception, match="Failed to execute SQL statement: 400"):
            await database.execute_sql("BROKEN SQL;")


@pytest.mark.asyncio
async def test_produce_message_success():
    producer = SimpleNamespace(
        start=AsyncMock(return_value=None),
        send_and_wait=AsyncMock(return_value=None),
        flush=AsyncMock(return_value=None),
        stop=AsyncMock(return_value=None),
    )
    with patch("tksessentials.database.get_default_kafka_producer", AsyncMock(return_value=producer)):
        await database.produce_message("topic1", "key1", {"v": 1})

    producer.send_and_wait.assert_awaited_once_with(topic="topic1", key="key1", value={"v": 1})
    producer.start.assert_not_awaited()
    producer.flush.assert_awaited_once()
    producer.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_produce_message_starts_kafka_producer_once():
    class Producer:
        def __init__(self, **kwargs):
            self.start = AsyncMock(return_value=None)
            self.send_and_wait = AsyncMock(return_value=None)
            self.flush = AsyncMock(return_value=None)
            self.stop = AsyncMock(return_value=None)

    producer = Producer()

    def _producer_factory(**kwargs):
        return producer

    with patch("tksessentials.database.get_kafka_cluster_brokers", return_value=["broker-1:9092"]):
        with patch("tksessentials.database.AIOKafkaProducer", side_effect=_producer_factory):
            await database.produce_message("topic1", "key1", {"v": 1})

    producer.start.assert_awaited_once()
    producer.send_and_wait.assert_awaited_once_with(topic="topic1", key="key1", value={"v": 1})
    producer.flush.assert_awaited_once()
    producer.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_produce_message_handles_kafka_error():
    producer = SimpleNamespace(
        start=AsyncMock(return_value=None),
        send_and_wait=AsyncMock(side_effect=KafkaError("kafka broken")),
        flush=AsyncMock(return_value=None),
        stop=AsyncMock(return_value=None),
    )
    with patch("tksessentials.database.get_default_kafka_producer", AsyncMock(return_value=producer)):
        with pytest.raises(Exception, match="An error occurred when trying to send a message"):
            await database.produce_message("topic1", "key1", {"v": 1})

    producer.flush.assert_awaited_once()
    producer.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_produce_message_handles_generic_error():
    producer = SimpleNamespace(
        start=AsyncMock(return_value=None),
        send_and_wait=AsyncMock(side_effect=RuntimeError("boom")),
        flush=AsyncMock(return_value=None),
        stop=AsyncMock(return_value=None),
    )
    with patch("tksessentials.database.get_default_kafka_producer", AsyncMock(return_value=producer)):
        with pytest.raises(Exception, match="A general error occurred when trying to send a message"):
            await database.produce_message("topic1", "key1", {"v": 1})

    producer.flush.assert_awaited_once()
    producer.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_availability_with_retry_all_services_available():
    async def is_kafka_available():
        return True

    def is_ksqldb_available():
        return True

    assert await database.check_availability_with_retry(
        [is_kafka_available, is_ksqldb_available],
        max_wait_time=1,
        poll_interval=1,
    ) is True


@pytest.mark.asyncio
async def test_check_availability_with_retry_times_out_on_failures():
    async def is_kafka_available():
        raise RuntimeError("kafka unavailable")

    def is_ksqldb_available():
        return False

    with patch("tksessentials.database.asyncio.sleep", AsyncMock(return_value=None)):
        with pytest.raises(TimeoutError):
            await database.check_availability_with_retry(
                [is_kafka_available, is_ksqldb_available],
                max_wait_time=1,
                poll_interval=1,
            )


@pytest.mark.asyncio
async def test_check_availability_with_retry_adds_false_for_unknown_check_failures():
    def flaky_check():
        raise RuntimeError("boom")

    with patch("tksessentials.database.asyncio.sleep", AsyncMock(return_value=None)):
        with pytest.raises(TimeoutError):
            await database.check_availability_with_retry(
                [flaky_check],
                max_wait_time=1,
                poll_interval=1,
            )


@pytest.mark.asyncio
async def test_check_availability_with_retry_reraises_non_retryable_check_errors():
    def bad_check():
        raise ValueError("bad check implementation")

    with patch("tksessentials.database.asyncio.sleep", AsyncMock(return_value=None)):
        with pytest.raises(ValueError, match="bad check implementation"):
            await database.check_availability_with_retry([bad_check], max_wait_time=1, poll_interval=1)


@pytest.mark.asyncio
async def test_execute_with_retries_eventual_success():
    state = {"attempts": 0}

    async def flaky_task():
        state["attempts"] += 1
        if state["attempts"] < 2:
            raise RuntimeError("transient failure")

    with patch("tksessentials.database.asyncio.sleep", AsyncMock(return_value=None)):
        await database.execute_with_retries(flaky_task, retries=3, delay=1)

    assert state["attempts"] == 2


@pytest.mark.asyncio
async def test_execute_with_retries_stops_immediately_on_non_retryable_errors():
    async def invalid_task():
        raise ValueError("invalid request")

    with patch("tksessentials.database.asyncio.sleep", AsyncMock(return_value=None)):
        with pytest.raises(ValueError):
            await database.execute_with_retries(invalid_task, retries=3, delay=1)


@pytest.mark.asyncio
async def test_execute_with_retries_raises_after_exhaustion():
    async def always_failing_task():
        raise RuntimeError("still failing")

    with patch("tksessentials.database.asyncio.sleep", AsyncMock(return_value=None)):
        with pytest.raises(Exception, match="Failed to execute SQL after"):
            await database.execute_with_retries(always_failing_task, retries=2, delay=1)


@pytest.mark.asyncio
async def test_create_topic_handles_non_matching_errors_and_transient_describe(monkeypatch):
    admin = SimpleNamespace(
        start=AsyncMock(return_value=None),
        create_topics=AsyncMock(
            return_value=SimpleNamespace(
                to_object=lambda: {
                    "topic_errors": [
                        {"topic": "other_topic", "error_code": 1},
                        {"topic": "orders", "error_code": 0},
                    ]
                }
            )
        ),
        describe_topics=AsyncMock(
            side_effect=[RuntimeError("temporary"), [{"topic": "orders", "partitions": [0]}]]
        ),
        close=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(database, "AIOKafkaAdminClient", lambda **kwargs: admin)
    monkeypatch.setattr(database, "NewTopic", lambda **kwargs: "topic_spec")
    monkeypatch.setattr(database, "get_kafka_cluster_brokers", lambda: ["broker:9092"])
    monkeypatch.setattr(database.asyncio, "sleep", AsyncMock(return_value=None))

    await database.create_topic("orders")
    admin.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_topic_raises_specific_error_from_error_code(monkeypatch):
    class CustomTopicError(Exception):
        pass

    admin = SimpleNamespace(
        start=AsyncMock(return_value=None),
        create_topics=AsyncMock(
            return_value=SimpleNamespace(
                to_object=lambda: {
                    "topic_errors": [
                        {"topic": "orders", "error_code": 33, "error_message": "custom failure"}
                    ]
                }
            )
        ),
        describe_topics=AsyncMock(return_value=[]),
        close=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(database, "AIOKafkaAdminClient", lambda **kwargs: admin)
    monkeypatch.setattr(database, "NewTopic", lambda **kwargs: "topic_spec")
    monkeypatch.setattr(database, "for_code", lambda code: CustomTopicError)
    monkeypatch.setattr(database, "get_kafka_cluster_brokers", lambda: ["broker:9092"])

    with pytest.raises(CustomTopicError, match="error_code=33\\): custom failure"):
        await database.create_topic("orders")

    admin.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_topic_catches_topic_already_exists(monkeypatch):
    admin = SimpleNamespace(
        start=AsyncMock(return_value=None),
        create_topics=AsyncMock(side_effect=TopicAlreadyExistsError("exists")),
        describe_topics=AsyncMock(return_value=[]),
        close=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(database, "AIOKafkaAdminClient", lambda **kwargs: admin)
    monkeypatch.setattr(database, "NewTopic", lambda **kwargs: "topic_spec")
    monkeypatch.setattr(database, "get_kafka_cluster_brokers", lambda: ["broker:9092"])

    await database.create_topic("orders")
    admin.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_topic_re_raises_kafka_error(monkeypatch):
    admin = SimpleNamespace(
        start=AsyncMock(return_value=None),
        create_topics=AsyncMock(side_effect=KafkaError("kafka down")),
        describe_topics=AsyncMock(return_value=[]),
        close=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(database, "AIOKafkaAdminClient", lambda **kwargs: admin)
    monkeypatch.setattr(database, "NewTopic", lambda **kwargs: "topic_spec")
    monkeypatch.setattr(database, "get_kafka_cluster_brokers", lambda: ["broker:9092"])

    with pytest.raises(KafkaError):
        await database.create_topic("orders")

    admin.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_read_compacted_state_snapshot_no_partitions_after_retry(monkeypatch):
    class FakeConsumer:
        def __init__(self, *args, **kwargs):
            self._assigned = set()

        async def start(self):
            return None

        async def stop(self):
            return None

        async def getmany(self, timeout_ms=0, max_records=None):
            return {}

        def assignment(self):
            return self._assigned

    fake_logger = SimpleNamespace(warning=Mock(), error=Mock())
    monkeypatch.setattr(database, "AIOKafkaConsumer", FakeConsumer)
    monkeypatch.setattr(database.asyncio, "sleep", AsyncMock(return_value=None))

    snapshot = await database.read_compacted_state_snapshot(
        topic="topic_x",
        bootstrap_servers=["broker1:9092", "broker2:9092"],
        logger=fake_logger,
        timeout_s=0.01,
        max_empty_polls=1,
    )

    assert snapshot == {}
    fake_logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_read_compacted_state_snapshot_empty_polls_stop_early(monkeypatch):
    tp = "topic_x-0"

    class FakeConsumer:
        def __init__(self, *args, **kwargs):
            self._assigned = {tp}
            self._end = {tp: 5}
            self._position = 0

        async def start(self):
            return None

        async def stop(self):
            return None

        async def getmany(self, timeout_ms=0, max_records=None):
            if timeout_ms <= 1:
                return {tp: []}
            return {tp: []}

        def assignment(self):
            return self._assigned

        async def seek_to_beginning(self, *partitions):
            self._position = 0

        async def end_offsets(self, partitions):
            return self._end

        async def position(self, partition):
            return self._position

    fake_logger = SimpleNamespace(warning=Mock(), error=Mock())
    monkeypatch.setattr(database, "AIOKafkaConsumer", FakeConsumer)

    snapshot = await database.read_compacted_state_snapshot(
        topic="topic_x",
        bootstrap_servers="broker1:9092",
        logger=fake_logger,
        timeout_s=0.01,
        max_empty_polls=1,
    )

    assert snapshot == {}


@pytest.mark.asyncio
async def test_read_compacted_state_snapshot_skips_malformed_and_tombstone(monkeypatch):
    class Msg:
        def __init__(self, key, value):
            self.key = key
            self.value = value

    tp = "topic_x-0"

    class FakeConsumer:
        def __init__(self, *args, **kwargs):
            self._assigned = {tp}
            self._end = {tp: 2}
            self._position = 0
            self._assignment_polled = False

        async def start(self):
            return None

        async def stop(self):
            return None

        async def getmany(self, timeout_ms=0, max_records=None):
            if timeout_ms <= 1 and not self._assignment_polled:
                self._assignment_polled = True
                return {tp: []}
            if self._position == 0:
                self._position = 2
                return {tp: [Msg(None, {"ignored": True}), Msg("ETH", None)]}
            return {tp: []}

        def assignment(self):
            return self._assigned

        async def seek_to_beginning(self, *partitions):
            self._position = 0

        async def end_offsets(self, partitions):
            return self._end

        async def position(self, partition):
            return self._position

    fake_logger = SimpleNamespace(warning=Mock(), error=Mock())
    monkeypatch.setattr(database, "AIOKafkaConsumer", FakeConsumer)

    snapshot = await database.read_compacted_state_snapshot(
        topic="topic_x",
        bootstrap_servers="broker1:9092",
        logger=fake_logger,
        timeout_s=0.01,
        max_empty_polls=2,
    )

    assert snapshot == {}


@pytest.mark.asyncio
async def test_read_compacted_state_snapshot_handles_kafka_error(monkeypatch):
    class BrokenConsumer:
        async def start(self):
            return None

        async def stop(self):
            return None

        async def getmany(self, timeout_ms=0, max_records=None):
            raise KafkaError("cannot poll")

        def assignment(self):
            return {"topic_x-0"}

    fake_logger = SimpleNamespace(warning=Mock(), error=Mock())
    monkeypatch.setattr(database, "AIOKafkaConsumer", lambda *args, **kwargs: BrokenConsumer())

    snapshot = await database.read_compacted_state_snapshot(
        topic="topic_x",
        bootstrap_servers="broker1:9092",
        logger=fake_logger,
        timeout_s=0.01,
        max_empty_polls=1,
    )

    assert snapshot == {}
    fake_logger.error.assert_called_once()


def test_deserialize_kafka_key_and_json_value_helpers():
    assert database.deserialize_kafka_key(b"abc") == "abc"
    assert database.deserialize_kafka_key(None) is None
    assert database.deserialize_kafka_json_value(b"{\"market\":\"BTC\"}") == {"market": "BTC"}
    assert database.deserialize_kafka_json_value(None) is None

    with pytest.raises(json.JSONDecodeError):
        database.deserialize_kafka_json_value(b"{")


def test_compose_consumer_id_and_producer_id(monkeypatch):
    monkeypatch.setattr(database.utils, "get_pod_name", lambda: "pod-123")

    assert database.compose_consumer_id() == "pod-123"
    assert database.compose_producer_id() == "pod-123"


def test_get_kafka_cluster_brokers_resolves_defaults(monkeypatch):
    monkeypatch.setattr(database.utils, "get_environment", lambda: "DEV")
    monkeypatch.setenv("KAFKA_BROKER_STRING", "NODES_NOT_DEFINED")
    assert database.get_kafka_cluster_brokers() == ["localhost:9092"]

    monkeypatch.setattr(database.utils, "get_environment", lambda: "PROD")
    monkeypatch.delenv("KAFKA_BROKER_STRING", raising=False)
    assert database.get_kafka_cluster_brokers() == ["localhost:9092"]


def test_table_or_view_exists_is_case_insensitive(monkeypatch):
    response = _Response(status_code=200, payload=[{"tables": [{"name": "Orders"}, {"name": "trades"}]}])
    with patch("tksessentials.database.httpx.post", return_value=response):
        assert database.table_or_view_exists("orders") is True


def test_table_or_view_exists_returns_false_if_absent(monkeypatch):
    response = _Response(status_code=200, payload=[{"tables": [{"name": "positions"}]}])
    with patch("tksessentials.database.httpx.post", return_value=response):
        assert database.table_or_view_exists("orders") is False


def test_table_or_view_exists_malformed_payload_returns_false(monkeypatch):
    response = _Response(status_code=200, payload={"tables": [{"name": "orders"}]})
    with patch("tksessentials.database.httpx.post", return_value=response):
        assert database.table_or_view_exists("orders") is False


def test_stream_exists_is_case_insensitive(monkeypatch):
    response = _Response(status_code=200, payload=[{"streams": [{"name": "Trades"}]}])
    with patch("tksessentials.database.httpx.post", return_value=response):
        assert database.stream_exists("trades") is True


def test_stream_exists_returns_false_if_absent(monkeypatch):
    response = _Response(status_code=200, payload=[{"streams": [{"name": "bookings"}]}])
    with patch("tksessentials.database.httpx.post", return_value=response):
        assert database.stream_exists("trades") is False


def test_stream_exists_malformed_payload_returns_false(monkeypatch):
    response = _Response(status_code=200, payload={"streams": [{"name": "trades"}]})
    with patch("tksessentials.database.httpx.post", return_value=response):
        assert database.stream_exists("trades") is False
