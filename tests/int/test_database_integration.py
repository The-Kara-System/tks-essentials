import asyncio
import time
import uuid

import pytest

from tksessentials import database


pytestmark = pytest.mark.integration


def _unique_name(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


async def _require_kafka() -> None:
    assert await database.is_kafka_available(), "Kafka should be available for integration tests."


def _require_ksqldb() -> None:
    assert database.is_ksqldb_available(), "ksqlDB should be available for integration tests."


async def _require_kafka_and_ksqldb() -> None:
    await _require_kafka()
    _require_ksqldb()


async def _wait_for_topic(topic_name: str, timeout_s: int = 30) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if await database.topic_exists(topic_name):
            return
        await asyncio.sleep(1)
    raise AssertionError(f"Topic {topic_name} did not become visible to consumers in time.")


def test_table_or_view_exists():
    _require_ksqldb()
    assert not database.table_or_view_exists(_unique_name("non_existent_table"))


@pytest.mark.asyncio
async def test_create_table():
    await _require_kafka_and_ksqldb()
    topic_name = _unique_name("test_topic")
    table_name = _unique_name("test_table")

    await database.create_topic(
        topic_name=topic_name,
        partitions=1,
        replication_factor=1,
        compacted=True,
    )
    await _wait_for_topic(topic_name)

    sql_statement = f"""
    CREATE TABLE {table_name}(
        event_timestamp BIGINT PRIMARY KEY,
        detail STRING,
        data STRING
    ) WITH (
        KAFKA_TOPIC='{topic_name}',
        VALUE_FORMAT='JSON',
        PARTITIONS=1
    );
    """

    await database.create_table(sql_statement, table_name)
    assert database.table_or_view_exists(table_name)


def test_stream_exists():
    _require_ksqldb()
    assert not database.stream_exists(_unique_name("non_existent_stream"))


@pytest.mark.asyncio
async def test_create_stream():
    await _require_kafka_and_ksqldb()
    topic_name = _unique_name("test_topic")
    stream_name = _unique_name("test_stream")

    await database.create_topic(
        topic_name=topic_name,
        partitions=1,
        replication_factor=1,
    )
    await _wait_for_topic(topic_name)

    sql_statement = f"""
    CREATE STREAM {stream_name}(
        event_timestamp BIGINT,
        detail STRING,
        data STRING
    ) WITH (
        KAFKA_TOPIC='{topic_name}',
        VALUE_FORMAT='JSON',
        PARTITIONS=1
    );
    """

    await database.create_stream(sql_statement, stream_name)
    assert database.stream_exists(stream_name)


@pytest.mark.asyncio
async def test_produce_message():
    await _require_kafka()
    topic_name = _unique_name("test_topic")
    test_key = "test_key"
    test_value = {"message": "test_value"}

    await database.create_topic(topic_name=topic_name, partitions=1, replication_factor=1)
    await _wait_for_topic(topic_name)
    consumer = await database.get_default_kafka_consumer(
        topic_name,
        auto_offset_reset="earliest",
        auto_commit=False,
    )

    try:
        await database.produce_message(topic_name, test_key, test_value)
        consumed_message = await asyncio.wait_for(consumer.getone(), timeout=10)
    finally:
        await consumer.stop()

    assert consumed_message.key == test_key
    assert consumed_message.value == test_value
