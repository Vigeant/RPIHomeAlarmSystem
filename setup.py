from distutils.core import setup

setup(
    name='RPIHomeAlarmSystem',
    version='13.8',
    author='Guillaume Vigeant',
    author_email='guillaume.vigeant@gmail.com',
    packages=['rpihomealarmsystem'],
    scripts=['bin/alarmSystem.sh','bin/alarmSystemStartupScriptUpdater.sh'],
    url='http://pypi.python.org/pypi/RPIHomeAlarmSystem/',
    license='LICENSE.txt',
    description='Raspberry Pi Home Alarm System',
    long_description=open('README.txt').read(),
    install_requires=[
        "PyDispatcher >= 2.0.3",
    ],
)