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
