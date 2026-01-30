from tksessentials import constants


def test_default_encoding():
    assert constants.DEFAULT_ENCODING == "utf-8"


def test_default_connection_timeout():
    assert constants.DEFAULT_CONNECTION_TIMEOUT == 60.0
