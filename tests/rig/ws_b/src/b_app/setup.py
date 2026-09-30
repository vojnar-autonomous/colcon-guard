import os
import time

from setuptools import setup

time.sleep(float(os.environ.get('GUARD_RIG_SLEEP', '0')))

package_name = 'b_app'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    extras_require={'test': ['pytest']},
    zip_safe=True,
)
