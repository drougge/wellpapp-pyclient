#!/usr/bin/env python3

from setuptools import setup

fuse_reqs = [
	'fuse-python >= 0.3.1; python_version < "3"',
	'fuse-python >= 1.0.0; python_version > "3"',
]

setup(
	name='wellpapp',
	version='CHANGEME.dev', # set this for each release

	packages=[
		'wellpapp',
		'wellpapp.shell',
	],
	entry_points={
		'console_scripts': [
			'wp = wellpapp.__main__:main',
		],
	},
	install_requires=[
		'Pillow >= 3.1.2',
		'PyGObject >= 3.20',
	],
	extras_require={
		'fuse': fuse_reqs,
		'all': fuse_reqs,
	},
	python_requires='>=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*',

	author='Carl Drougge',
	author_email='bearded@longhaired.org',
	url='https://github.com/drougge/wellpapp-pyclient',
	license='MIT',
	description='Client library and application for the wellpapp image tagging system.',
	long_description=open('README.md', 'r').read(),
	long_description_content_type='text/markdown',
)
