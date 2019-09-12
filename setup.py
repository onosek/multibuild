#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

setup(
    name='multibuild',
    version='0.4.1',
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
        # "brewkoji",
        # "jq",
    ],
    python_requires='>=3',
    test_suite='nose.collector',
    packages=find_packages(),
    scripts=['bin/multibuild'],
    include_package_data=True,
    data_files=[('~/.config/multibuild', ['conf/multibuild.conf'])],)
