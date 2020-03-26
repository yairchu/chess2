from setuptools import setup

OPTIONS = {
    'packages': ['kivy', 'stun'],
}

setup(
    name='Chess Chase',
    app=['main.py'],
    data_files=['chess.png'],
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
