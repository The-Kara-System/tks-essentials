import asyncio
import time
import uuid

import pytest
from aiokafka.admin import AIOKafkaAdminClient
from aiokafka.admin.config_resource import ConfigResource, ConfigResourceType

from tksessentials import database

DEFAULT_TIMEOUT_SECONDS = 30
POLL_INTERVAL_SECONDS = 1


async def _require_kafka() -> None:
    if not await database.is_kafka_available():
        pytest.skip("Kafka is not available for integration tests.")


async def _wait_for_topic(topic_name: str, should_exist: bool) -> None:
    deadline = time.monotonic() + DEFAULT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        metadata = await _get_topic_metadata(topic_name)
        if should_exist:
            if metadata and metadata.get("error_code", 0) == 0 and metadata.get("partitions"):
                return
        else:
            if not metadata or metadata.get("error_code", 0) != 0 or not metadata.get("partitions"):
                return
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    state = "exist" if should_exist else "be deleted"
    raise AssertionError(f"Timed out waiting for topic {topic_name} to {state}.")


async def _wait_for_cleanup_policy(topic_name: str) -> str:
    deadline = time.monotonic() + DEFAULT_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        configs = await _get_topic_configs(topic_name)
        policy = configs.get("cleanup.policy")
        if policy:
            return policy
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    raise AssertionError(f"Timed out waiting for cleanup.policy for topic {topic_name}.")


async def _get_topic_metadata(topic_name: str) -> dict | None:
    brokers = database.get_kafka_cluster_brokers()
    broker_str = brokers if isinstance(brokers, str) else ",".join(brokers)
    admin = AIOKafkaAdminClient(bootstrap_servers=broker_str)
    await admin.start()
    try:
        topics = await admin.describe_topics([topic_name])
    finally:
        await admin.close()

    for topic in topics:
        if topic.get("topic") == topic_name:
            return topic
    return None


async def _get_topic_configs(topic_name: str) -> dict[str, str]:
    brokers = database.get_kafka_cluster_brokers()
    broker_str = brokers if isinstance(brokers, str) else ",".join(brokers)
    admin = AIOKafkaAdminClient(bootstrap_servers=broker_str)
    await admin.start()
    try:
        resources = [ConfigResource(ConfigResourceType.TOPIC, topic_name)]
        responses = await admin.describe_configs(resources)
    finally:
        await admin.close()

    configs: dict[str, str] = {}
    for response in responses:
        for resource in response.resources:
            resource_name = resource.resource_name if hasattr(resource, "resource_name") else resource[3]
            config_entries = resource.config_entries if hasattr(resource, "config_entries") else resource[4]
            if resource_name != topic_name:
                continue
            for entry in config_entries:
                config_name = entry.config_names if hasattr(entry, "config_names") else entry[0]
                config_value = entry.config_value if hasattr(entry, "config_value") else entry[1]
                configs[config_name] = config_value
    return configs


async def _delete_topic(topic_name: str) -> None:
    brokers = database.get_kafka_cluster_brokers()
    broker_str = brokers if isinstance(brokers, str) else ",".join(brokers)
    admin = AIOKafkaAdminClient(bootstrap_servers=broker_str)
    await admin.start()
    try:
        await admin.delete_topics([topic_name])
    finally:
        await admin.close()


@pytest.mark.asyncio
async def test_create_topic_cleanup_policy_defaults_to_delete():
    await _require_kafka()
    topic_name = f"int_policy_default_{uuid.uuid4().hex}"

    await database.create_topic(topic_name, partitions=1, replication_factor=1)

    try:
        await _wait_for_topic(topic_name, should_exist=True)
        cleanup_policy = await _wait_for_cleanup_policy(topic_name)
        assert cleanup_policy == "delete"
    finally:
        await _delete_topic(topic_name)
        await _wait_for_topic(topic_name, should_exist=False)


@pytest.mark.asyncio
async def test_create_topic_cleanup_policy_compacted_boolean():
    await _require_kafka()
    topic_name = f"int_policy_compact_{uuid.uuid4().hex}"

    await database.create_topic(topic_name, partitions=1, replication_factor=1, compacted=True)

    try:
        await _wait_for_topic(topic_name, should_exist=True)
        cleanup_policy = await _wait_for_cleanup_policy(topic_name)
        assert cleanup_policy == "compact"
    finally:
        await _delete_topic(topic_name)
        await _wait_for_topic(topic_name, should_exist=False)


@pytest.mark.asyncio
async def test_create_topic_cleanup_policy_delete_and_compact():
    await _require_kafka()
    topic_name = f"int_policy_dual_{uuid.uuid4().hex}"

    await database.create_topic(
        topic_name,
        partitions=1,
        replication_factor=1,
        cleanup_policy="delete,compact",
    )

    try:
        await _wait_for_topic(topic_name, should_exist=True)
        cleanup_policy = await _wait_for_cleanup_policy(topic_name)
        assert cleanup_policy == "delete,compact"
    finally:
        await _delete_topic(topic_name)
        await _wait_for_topic(topic_name, should_exist=False)


@pytest.mark.asyncio
async def test_create_topic_cleanup_policy_list_input():
    await _require_kafka()
    topic_name = f"int_policy_list_{uuid.uuid4().hex}"

    await database.create_topic(
        topic_name,
        partitions=1,
        replication_factor=1,
        cleanup_policy=["delete", "compact"],
    )

    try:
        await _wait_for_topic(topic_name, should_exist=True)
        cleanup_policy = await _wait_for_cleanup_policy(topic_name)
        assert cleanup_policy == "delete,compact"
    finally:
        await _delete_topic(topic_name)
        await _wait_for_topic(topic_name, should_exist=False)
