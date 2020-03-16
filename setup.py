from setuptools import setup

OPTIONS = {
    'packages': ['pygame', 'stun'],
}

setup(
    name='Chess 2',
    app=['main.py'],
    data_files=['chess.png'],
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
