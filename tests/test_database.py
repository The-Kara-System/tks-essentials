import time
from types import SimpleNamespace
import pytest
from tksessentials import database, utils
from tksessentials.database import KSQLNotReadyError
from unittest.mock import patch, AsyncMock
import httpx

@pytest.fixture(scope="module")
def setup():
    print("\n")
    print("REMINDER. All tests require a Kafka broker and a ksqlDB instance to be available.")
    print(f"\tENV: {utils.get_environment()}")
    print(f"\tkafka: {database.get_kafka_cluster_brokers()}")
    print(f"\tksqldb: {database.get_ksqldb_url()}")

def test_get_kafka_cluster_brokers_dev():
    # Mock utils.get_environment() to return 'DEV'
    with patch('tksessentials.utils.get_environment', return_value='DEV'):
        brokers = database.get_kafka_cluster_brokers()
        # Check if the returned brokers are as expected
        assert brokers == ['localhost:9092']

def test_get_kafka_cluster_brokers_non_dev():
    # Mock utils.get_environment() to return 'PROD'
    with patch('tksessentials.utils.get_environment', return_value='PROD'):
        # Mock os.getenv to return a specific broker string
        with patch('os.getenv', return_value='broker1.svc.cluster.local:9092,broker2.svc.cluster.local:9093'):
            brokers = database.get_kafka_cluster_brokers()
            # Check if the returned brokers contain the expected substring
            assert 'broker1.svc.cluster.local:9092' in brokers
            assert brokers == ['broker1.svc.cluster.local:9092', 'broker2.svc.cluster.local:9093']

@pytest.mark.parametrize(
    "value,expected",
    [
        (None, ["localhost:9092"]),
        ("", ["localhost:9092"]),
        ("   ", ["localhost:9092"]),
        ("NODES_NOT_DEFINED", ["localhost:9092"]),
        (" broker1:9092 , ,broker2:9093,, ", ["broker1:9092", "broker2:9093"]),
        ([" broker1:9092 ", "", "broker2:9093", "   "], ["broker1:9092", "broker2:9093"]),
        (("broker1:9092", "broker2:9093"), ["broker1:9092", "broker2:9093"]),
        (["", "   "], ["localhost:9092"]),
        (123, ["localhost:9092"]),
    ],
)
def test_normalize_broker_list(value, expected):
    assert database._normalize_broker_list(value) == expected

def test_table_or_view_exists():
    max_retries = 5
    delay = 10  # seconds

    for attempt in range(max_retries):
        try:
            assert not database.table_or_view_exists("NON_EXISTENT_TABLE")
            break
        except (
            httpx.ConnectError,
            KSQLNotReadyError,
            httpx.RemoteProtocolError,
            httpx.ReadError,
        ) as e:
            if attempt < max_retries - 1:
                print(
                    f"Attempt {attempt + 1}/{max_retries} failed with error: {e}. Retrying in {delay} seconds..."
                )
                time.sleep(delay)
            else:
                raise
        except Exception as e:
            print(f"Test failed with an unexpected error: {e}. {e.args}")
            raise

@pytest.mark.asyncio
async def test_create_table():
    table_name = "TEST_TABLE"
    topic_name = "test_topic"

    await database.create_topic(
        topic_name=topic_name,
        partitions=1,
        replication_factor=1,  # or 3 in prod; tests usually 1
        compacted=True,        # optional; table topics are commonly compacted
    )

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

@pytest.mark.asyncio
async def test_prepare_sql_statement():
    sql_statement = """
    CREATE TABLE TEST_TABLE_PARTITION(
        event_timestamp BIGINT PRIMARY KEY,
        detail STRING,
        data STRING,
        signal_data STRUCT<
            provider_signal_id STRING,
            provider_trade_id STRING,
            provider_id STRING,
            strategy_id STRING,
            is_hot_signal BOOLEAN,
            market STRING,
            data_source STRING,
            direction STRING,
            side STRING,
            order_type STRING,
            price DOUBLE,
            tp DOUBLE,
            sl DOUBLE,
            position_size_in_percentage INT,
            date_of_creation BIGINT
        >,
        ip STRING
    ) WITH (
        KAFKA_TOPIC='test_topic_partition',
        VALUE_FORMAT='JSON',
        TIMESTAMP='event_timestamp',
        PARTITIONS=6
    );
    """

    with patch('tksessentials.database.topic_exists', return_value=True):
        prepared_statement = await database.prepare_sql_statement(sql_statement)
        assert "PARTITIONS=6" not in prepared_statement

    with patch('tksessentials.database.topic_exists', return_value=False):
        prepared_statement = await database.prepare_sql_statement(sql_statement)
        assert "PARTITIONS=6" in prepared_statement

@pytest.mark.asyncio
async def test_prepare_sql_statement_missing():
    """This test checks if the preparation works as well, wenn there is no PARTITION?"""
    sql_statement = """
    CREATE TABLE TEST_TABLE_PARTITION(
        event_timestamp BIGINT PRIMARY KEY,
        detail STRING,
        data STRING,
        signal_data STRUCT<
            provider_signal_id STRING,
            provider_trade_id STRING,
            provider_id STRING,
            strategy_id STRING,
            is_hot_signal BOOLEAN,
            market STRING,
            data_source STRING,
            direction STRING,
            side STRING,
            order_type STRING,
            price DOUBLE,
            tp DOUBLE,
            sl DOUBLE,
            position_size_in_percentage INT,
            date_of_creation BIGINT
        >,
        ip STRING
    ) WITH (
        KAFKA_TOPIC='test_topic_partition',
        VALUE_FORMAT='JSON',
        TIMESTAMP='event_timestamp'
    );
    """

    with patch('tksessentials.database.topic_exists', return_value=True):
        prepared_statement = await database.prepare_sql_statement(sql_statement)
        assert "PARTITIONS=6" not in prepared_statement

    with patch('tksessentials.database.topic_exists', return_value=False):
        prepared_statement = await database.prepare_sql_statement(sql_statement)
        assert "PARTITIONS=6" in prepared_statement

def test_clean_sql_statement():
    sql_statement = """
    CREATE TABLE fa_signal_processing_trading_signal_received(
        event_timestamp BIGINT PRIMARY KEY,
        detail STRING,
        data STRING,
        signal_data STRUCT<
            provider_signal_id STRING,
            provider_trade_id STRING,
            provider_id STRING,
            strategy_id STRING,
            is_hot_signal BOOLEAN,
            market STRING,
            data_source STRING,
            direction STRING,
            side STRING,
            order_type STRING,
            price DOUBLE,
            tp DOUBLE,
            sl DOUBLE,
            position_size_in_percentage INT,
            date_of_creation BIGINT
        >,
        ip STRING
    ) WITH (
        KAFKA_TOPIC='fa_signal_processing.trading_signal_received',
        VALUE_FORMAT='JSON',
        TIMESTAMP='event_timestamp',
        PARTITIONS=6
    );
    """

    expected_cleaned_sql = "CREATE TABLE fa_signal_processing_trading_signal_received( event_timestamp BIGINT PRIMARY KEY, detail STRING, data STRING, signal_data STRUCT< provider_signal_id STRING, provider_trade_id STRING, provider_id STRING, strategy_id STRING, is_hot_signal BOOLEAN, market STRING, data_source STRING, direction STRING, side STRING, order_type STRING, price DOUBLE, tp DOUBLE, sl DOUBLE, position_size_in_percentage INT, date_of_creation BIGINT >, ip STRING ) WITH ( KAFKA_TOPIC='fa_signal_processing.trading_signal_received', VALUE_FORMAT='JSON', TIMESTAMP='event_timestamp', PARTITIONS=6 );"

    cleaned_sql = database.clean_sql_statement(sql_statement)
    assert cleaned_sql == expected_cleaned_sql

def test_stream_exists():
    max_retries = 5
    delay = 10  # seconds

    for attempt in range(max_retries):
        try:
            assert not database.stream_exists("NON_EXISTENT_STREAM")
            break
        except (
            httpx.ConnectError,
            KSQLNotReadyError,
            httpx.RemoteProtocolError,
            httpx.ReadError,
        ) as e:
            if attempt < max_retries - 1:
                print(
                    f"Attempt {attempt + 1}/{max_retries} failed with error: {e}. Retrying in {delay} seconds..."
                )
                time.sleep(delay)
            else:
                raise
        except Exception as e:
            print(f"Test failed with an unexpected error: {e}. {e.args}")
            raise

@pytest.mark.asyncio
async def test_create_stream():
    STREAM_NAME = "TEST_STREAM"
    sql_statement = f"""
    CREATE STREAM {STREAM_NAME}(
        event_timestamp BIGINT,
        detail STRING,
        data STRING
    ) WITH (
        KAFKA_TOPIC='test_topic',
        VALUE_FORMAT='JSON',
        PARTITIONS=1
    );
    """

    max_retries = 5
    delay = 10  # seconds

    for attempt in range(max_retries):
        try:
            await database.create_stream(sql_statement, STREAM_NAME)
            assert database.stream_exists(STREAM_NAME)
            break
        except (
            httpx.ConnectError,
            KSQLNotReadyError,
            httpx.RemoteProtocolError,
            httpx.ReadError,
        ) as e:
            if attempt < max_retries - 1:
                print(
                    f"Attempt {attempt + 1}/{max_retries} failed with error: {e}. Retrying in {delay} seconds..."
                )
                time.sleep(delay)
            else:
                raise
        except Exception as e:
            print(f"Test failed with an unexpected error: {e}")
            raise

@pytest.mark.asyncio
async def test_create_topic_defaults():
    admin_instance = AsyncMock()
    admin_instance.start = AsyncMock()
    admin_instance.create_topics = AsyncMock(
        return_value=SimpleNamespace(to_object=lambda: {"topic_errors": []})
    )
    admin_instance.close = AsyncMock()

    with patch('tksessentials.database.AIOKafkaAdminClient', return_value=admin_instance) as admin_cls:
        with patch('tksessentials.database.NewTopic', return_value="topic_spec") as new_topic_cls:
            await database.create_topic("test_topic")

    admin_cls.assert_called_once()
    new_topic_cls.assert_called_once()
    kwargs = new_topic_cls.call_args.kwargs
    assert kwargs["name"] == "test_topic"
    assert kwargs["num_partitions"] == 6
    assert kwargs["replication_factor"] == 2
    assert kwargs["topic_configs"]["cleanup.policy"] == "delete"
    assert kwargs["topic_configs"]["retention.ms"] == "-1"
    assert kwargs["topic_configs"]["retention.bytes"] == "-1"
    admin_instance.create_topics.assert_awaited_once_with(new_topics=["topic_spec"], validate_only=False)

@pytest.mark.asyncio
async def test_create_topic_compacted():
    admin_instance = AsyncMock()
    admin_instance.start = AsyncMock()
    admin_instance.create_topics = AsyncMock(
        return_value=SimpleNamespace(to_object=lambda: {"topic_errors": []})
    )
    admin_instance.close = AsyncMock()

    with patch('tksessentials.database.AIOKafkaAdminClient', return_value=admin_instance):
        with patch('tksessentials.database.NewTopic', return_value="topic_spec") as new_topic_cls:
            await database.create_topic("test_topic", compacted=True)

    kwargs = new_topic_cls.call_args.kwargs
    assert kwargs["topic_configs"]["cleanup.policy"] == "compact"
    assert kwargs["topic_configs"]["retention.ms"] == "-1"
    assert kwargs["topic_configs"]["retention.bytes"] == "-1"


@pytest.mark.asyncio
async def test_snapshot_returns_latest_value_for_same_key(monkeypatch):
    class Msg:
        def __init__(self, key, value):
            self.key = key
            self.value = value

    class TP:
        def __init__(self, topic, partition):
            self.topic = topic
            self.partition = partition
        def __hash__(self):
            return hash((self.topic, self.partition))
        def __eq__(self, other):
            return (self.topic, self.partition) == (other.topic, other.partition)

    tp0 = TP("test_topic", 0)

    messages = [
        Msg("BTC", {"v": 1}),
        Msg("ETH", {"v": 10}),
        Msg("BTC", {"v": 2}),  # latest wins
    ]

    class FakeConsumer:
        def __init__(self, *args, **kwargs):
            self._assigned = {tp0}
            self._end_offsets = {tp0: len(messages)}
            self._pos = {tp0: 0}
            self._assignment_poll_done = False

        async def start(self): return
        async def stop(self): return

        def assignment(self):
            return self._assigned

        async def seek_to_beginning(self, *partitions):
            self._pos[tp0] = 0

        async def end_offsets(self, partitions):
            return self._end_offsets

        async def position(self, tp):
            return self._pos[tp]

        async def getmany(self, timeout_ms=0, max_records=None):
            # 1) First poll(s) in your function are only to trigger assignment.
            #    We must NOT consume any data there.
            if timeout_ms <= 1 and not self._assignment_poll_done:
                self._assignment_poll_done = True
                return {tp0: []}

            # 2) After seek_to_beginning(), read from current position
            start = self._pos[tp0]
            if start >= len(messages):
                return {tp0: []}

            end = len(messages) if max_records is None else min(len(messages), start + max_records)
            batch = messages[start:end]
            self._pos[tp0] = end
            return {tp0: batch}

    # Patch where AIOKafkaConsumer is looked up.
    monkeypatch.setattr(database, "AIOKafkaConsumer", FakeConsumer)

    class Logger:
        def warning(self, *_): pass
        def error(self, *_): pass

    snapshot = await database.read_compacted_state_snapshot(
        topic="test_topic",
        bootstrap_servers="localhost:9092",
        logger=Logger(),
        timeout_s=0.1,
        max_empty_polls=2,  # can stay 1 too; 2 is just extra safe
    )

    assert snapshot["BTC"] == {"v": 2}
    assert snapshot["ETH"] == {"v": 10}
