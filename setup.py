#!/usr/bin/env python

from setuptools import setup
import versioneer

with open('requirements.txt', 'r') as fp:
  requirements = list(filter(bool, (line.strip() for line in fp)))
with open('README.md', 'rb') as fp:
  long_description = fp.read().decode('utf-8')

setup(
  name='remote_kernel',

  author='Joost van Griethuysen',
  author_email='joostjm@gmail.com',

  version=versioneer.get_version(),

  packages=['remote_kernel'],
  package_data={'remote_kernel': ['resources/*.png']},
  zip_safe=False,

  description='Python Script to connect to remote IPyKernel via ssh',
  long_description=long_description,
  long_description_content_type='text/markdown',

  license='BSD License',

  classifiers=[
    'Development Status :: 1 - Planning',
    'Environment :: Console',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: BSD License',
    'Operating System :: Microsoft :: Windows',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.5',
    'Topic :: Utilities'
  ],

  install_requires=requirements,

  keywords='remote-kernel,ipykernel,ssh'
)
