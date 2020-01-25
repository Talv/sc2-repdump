#!/usr/bin/env python3

from distutils.core import setup
from s2repdump.types import S2REPDUMP_VERSION

setup(
    name='s2repdump',
    version=S2REPDUMP_VERSION,
    author='Talv',
    url='https://github.com/Talv/s2repdump',
    packages=['s2repdump'],
    entry_points={
        'console_scripts': [
            's2repdump=s2repdump.main:cli',
        ]
    },
    python_requires='>=3.6',
    install_requires=[
        's2protocol',
        'tabulate',
        'colorlog',
        'more-itertools',
    ],
)
