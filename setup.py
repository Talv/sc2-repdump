#!/usr/bin/env python2

from distutils.core import setup

setup(
    name='s2repdump',
    version='0.1.0',
    author='Talv',
    url='https://github.com/Talv/s2repdump',
    packages=['s2repdump'],
    entry_points={
        'console_scripts': [
            's2repdump=s2repdump.main:main',
        ]
    },
    install_requires=[
        's2protocol'
    ],
)
