from setuptools import find_packages, setup

package_name = 'aura_ros2_bridge'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Antigravity Engineer',
    maintainer_email='dhyan2006@gmail.com',
    description='ROS 2 bridge connecting AURA Agent Tools to ROS 2 actions and perception topics',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'nav2_client = aura_ros2_bridge.nav2_client_node:main',
            'perception_bridge = aura_ros2_bridge.perception_bridge_node:main',
        ],
    },
)
