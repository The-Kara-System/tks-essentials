import asyncio
import time
import uuid

import pytest
from aiokafka.admin import AIOKafkaAdminClient
from aiokafka.admin.config_resource import ConfigResource, ConfigResourceType

from tksessentials import database

DEFAULT_TIMEOUT_SECONDS = 30
POLL_INTERVAL_SECONDS = 1


def _normalize_brokers(brokers: list[str] | str) -> list[str]:
    if isinstance(brokers, str):
        return [broker.strip() for broker in brokers.split(",") if broker.strip()]
    return brokers


async def _wait_for_topic(topic_name: str, should_exist: bool) -> dict | None:
    deadline = time.monotonic() + DEFAULT_TIMEOUT_SECONDS
    last_metadata = None
    while time.monotonic() < deadline:
        metadata = await _get_topic_metadata(topic_name)
        last_metadata = metadata
        if should_exist:
            if metadata and metadata.get("error_code", 0) == 0 and metadata.get("partitions"):
                return metadata
        else:
            if not metadata or metadata.get("error_code", 0) != 0 or not metadata.get("partitions"):
                return metadata
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
    state = "exist" if should_exist else "be deleted"
    raise AssertionError(
        f"Timed out waiting for topic {topic_name} to {state}. Last metadata: {last_metadata}"
    )


async def _get_topic_configs(topic_name: str) -> dict:
    brokers = database.get_kafka_cluster_brokers()
    broker_str = brokers if isinstance(brokers, str) else ",".join(brokers)
    admin = AIOKafkaAdminClient(bootstrap_servers=broker_str)
    await admin.start()
    try:
        resources = [ConfigResource(ConfigResourceType.TOPIC, topic_name)]
        responses = await admin.describe_configs(resources)
    finally:
        await admin.close()

    configs = {}
    for response in responses:
        for resource in response.resources:
            if hasattr(resource, "resource_name"):
                resource_name = resource.resource_name
                config_entries = resource.config_entries
            else:
                resource_name = resource[3]
                config_entries = resource[4]

            if resource_name != topic_name:
                continue

            for entry in config_entries:
                if hasattr(entry, "config_names"):
                    config_name = entry.config_names
                    config_value = entry.config_value
                else:
                    config_name = entry[0]
                    config_value = entry[1]
                configs[config_name] = config_value
    return configs


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


async def _get_cluster_metadata() -> dict:
    brokers = database.get_kafka_cluster_brokers()
    broker_str = brokers if isinstance(brokers, str) else ",".join(brokers)
    admin = AIOKafkaAdminClient(bootstrap_servers=broker_str)
    await admin.start()
    try:
        cluster = await admin.describe_cluster()
    finally:
        await admin.close()
    return cluster


async def _require_min_brokers(min_brokers: int) -> int:
    cluster = await _get_cluster_metadata()
    brokers = cluster.get("brokers", [])
    broker_count = len(brokers)
    if broker_count < min_brokers:
        pytest.skip(f"Requires at least {min_brokers} brokers; found {broker_count}.")
    bootstrap_brokers = _normalize_brokers(database.get_kafka_cluster_brokers())
    advertised_brokers = {f"{broker.get('host')}:{broker.get('port')}" for broker in brokers}
    print(f"Bootstrap brokers: {bootstrap_brokers}")
    print(f"Advertised brokers: {sorted(advertised_brokers)}")
    if bootstrap_brokers and advertised_brokers:
        if not set(bootstrap_brokers).intersection(advertised_brokers):
            raise AssertionError(
                "Bootstrap brokers do not match advertised listeners. "
                "Check KAFKA_BROKER_STRING and Kafka advertised.listeners."
            )
    return broker_count


def _extract_replication_and_partitions(topic_metadata: dict) -> tuple[int, int]:
    partitions = topic_metadata.get("partitions", [])
    if not partitions:
        raise AssertionError(f"No partitions found in metadata: {topic_metadata}")

    replication_factors = {len(partition.get("replicas", [])) for partition in partitions}
    if len(replication_factors) != 1:
        raise AssertionError(
            f"Unexpected replication factor spread: {replication_factors} from {topic_metadata}"
        )

    return replication_factors.pop(), len(partitions)


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
async def test_compacted_topic_lifecycle():
    await _require_min_brokers(3)
    topic_name = f"compacted_topic_{uuid.uuid4().hex}"
    await database.create_topic(
        topic_name,
        partitions=1,
        replication_factor=1,
        compacted=True,
    )

    try:
        await _wait_for_topic(topic_name, should_exist=True)
        configs = await _get_topic_configs(topic_name)
        cleanup_policy = configs.get("cleanup.policy", "")
        assert "compact" in cleanup_policy
    finally:
        await _delete_topic(topic_name)
        await _wait_for_topic(topic_name, should_exist=False)


@pytest.mark.asyncio
async def test_replication_factor_explicit_two():
    await _require_min_brokers(3)
    topic_name = f"replication_two_{uuid.uuid4().hex}"
    await database.create_topic(topic_name, replication_factor=2)
    await asyncio.sleep(10)  # Allow some time for the topic to be fully created before checking metadata

    try:
        metadata = await _wait_for_topic(topic_name, should_exist=True)
        configs = await _get_topic_configs(topic_name)
        print(f"Topic metadata for {topic_name}: {metadata}")
        print(f"Topic configs for {topic_name}: {configs}")
        replication_factor, _ = _extract_replication_and_partitions(metadata)
        assert replication_factor == 2
    finally:
        await _delete_topic(topic_name)
        await _wait_for_topic(topic_name, should_exist=False)
        

@pytest.mark.asyncio
async def test_replication_factor_default_two():
    await _require_min_brokers(3)
    topic_name = f"replication_default_{uuid.uuid4().hex}"
    await database.create_topic(topic_name)

    try:
        metadata = await _wait_for_topic(topic_name, should_exist=True)
        configs = await _get_topic_configs(topic_name)
        print(f"Topic metadata for {topic_name}: {metadata}")
        print(f"Topic configs for {topic_name}: {configs}")
        replication_factor, _ = _extract_replication_and_partitions(metadata)
        assert replication_factor == 2
    finally:
        await _delete_topic(topic_name)
        await _wait_for_topic(topic_name, should_exist=False)


@pytest.mark.asyncio
async def test_replication_factor_three():
    await _require_min_brokers(3)
    topic_name = f"replication_three_{uuid.uuid4().hex}"
    await database.create_topic(topic_name, replication_factor=3)

    try:
        metadata = await _wait_for_topic(topic_name, should_exist=True)
        configs = await _get_topic_configs(topic_name)
        print(f"Topic metadata for {topic_name}: {metadata}")
        print(f"Topic configs for {topic_name}: {configs}")
        replication_factor, _ = _extract_replication_and_partitions(metadata)
        assert replication_factor == 3
    finally:
        await _delete_topic(topic_name)
        await _wait_for_topic(topic_name, should_exist=False)


@pytest.mark.asyncio
async def test_partitions_default_six():
    await _require_min_brokers(3)
    topic_name = f"partitions_default_{uuid.uuid4().hex}"
    await database.create_topic(topic_name)
    await asyncio.sleep(10)  # Allow some time for the topic to be fully created before checking metadata

    try:
        metadata = await _wait_for_topic(topic_name, should_exist=True)
        configs = await _get_topic_configs(topic_name)
        print(f"Topic metadata for {topic_name}: {metadata}")
        print(f"Topic configs for {topic_name}: {configs}")
        _, partition_count = _extract_replication_and_partitions(metadata)
        assert partition_count == 6
    finally:
        await _delete_topic(topic_name)
        await _wait_for_topic(topic_name, should_exist=False)


@pytest.mark.asyncio
async def test_partitions_custom_three():
    await _require_min_brokers(3)
    topic_name = f"partitions_three_{uuid.uuid4().hex}"
    await database.create_topic(topic_name, partitions=3)

    try:
        metadata = await _wait_for_topic(topic_name, should_exist=True)
        configs = await _get_topic_configs(topic_name)
        print(f"Topic metadata for {topic_name}: {metadata}")
        print(f"Topic configs for {topic_name}: {configs}")
        _, partition_count = _extract_replication_and_partitions(metadata)
        assert partition_count == 3
    finally:
        await _delete_topic(topic_name)
        await _wait_for_topic(topic_name, should_exist=False)
