#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import find_packages, setup

setup(
    name='multibuild',
    version='0.6.1',
    description='speed up operations during release process',
    author='Ondřej Nosek',
    author_email='onosek@redhat.com',
    url='https://github.com/onosek/multibuild',
    license='GPLv3+',
    classifiers=[
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Programming Language :: Python :: 3 :: Only",
    ],
    install_requires=[
        # "python3-koji",
        # "git",
        # "rhpkg",
        # "fedpkg",
        # "brewkoji",
        # "jq",
    ],
    python_requires='>=3',
    test_suite='nose.collector',
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'multibuild = multibuild.__main__:main',
        ]
    },
    include_package_data=True,
    data_files=[('multibuild', ['conf/multibuild.conf'])],)
