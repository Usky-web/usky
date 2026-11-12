from setuptools import find_packages, setup

package_name = 'm1_three'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/m1_three.launch.py']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Usky',
    maintainer_email='3601171306@qq.com',
    description='M1-3：静态 TF 树 + 时间同步 + 激光点云投影',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'static_tf_publisher = m1_three.static_tf_publisher:main',
            'projection_node = m1_three.projection_node:main',
            'slop_scan = m1_three.slop_scan:main',
        ],
    },
)
