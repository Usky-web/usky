import os

from setuptools import find_packages, setup

package_name = 'smartcar_m1_ns'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/bringup.launch.py']),
        ('share/' + package_name + '/params',
         ['params/params_robot1.yaml', 'params/params_robot2.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Usky',
    maintainer_email='3601171306@qq.com',
    description='M1-2 可命名空间化的三节点 + bringup.launch.py 一键启动',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'node_a_sensor = smartcar_m1_ns.node_a_sensor:main',
            'node_b_filter = smartcar_m1_ns.node_b_filter:main',
            'node_c_alarm = smartcar_m1_ns.node_c_alarm:main',
        ],
    },
)
