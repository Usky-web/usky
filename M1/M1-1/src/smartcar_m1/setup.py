from setuptools import find_packages, setup

package_name = 'smartcar_m1'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Usky',
    maintainer_email='3601171306@qq.com',
    description='M1-1 三节点链路：模拟传感器 -> 一阶低通滤波 -> 报警响应',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'node_a_sensor = smartcar_m1.node_a_sensor:main',
            'node_b_filter = smartcar_m1.node_b_filter:main',
            'node_c_alarm = smartcar_m1.node_c_alarm:main',
            'alarm_server = smartcar_m1.alarm_server:main',
        ],
    },
)
