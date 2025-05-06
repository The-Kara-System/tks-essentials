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
    # packages=['tksessentials'],
    # package_dir={'tksessentials':'src'}
    # packages=find_packages(),
    # version='0.1.0',
    # description='The library describes the most common models used in trading systems.',
    # author='Brayan Svan',
    # license='MIT',
    # install_requires=['sqlmodel'],
    # setup_requires=['pytest-runner'],
    # tests_require=['pytest==4.4.1'],
    # test_suite='tests',
    # cmdclass={
    #     'build': ProduceAvroSchemas,
    # },
)
