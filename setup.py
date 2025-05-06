from setuptools import find_packages, setup

setup(
    name="tks-essentials",
    packages=find_packages(
        include=[
            "tksessentials",
            # 'tksessentials.models',
        ],
        exclude=["tests*"],
    ),
    install_requires=[
        "confluent-kafka>=2.4.0",
        "aiokafka>=0.10.0",
        "kafka_python>=2.0.2",
        "cryptography>=42.0.5",
        "email-validator>=2.1.1",
        "httpx>=0.27.0",
        "pyyaml>=6.0.1",
    ]
)
