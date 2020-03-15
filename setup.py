from setuptools import setup

OPTIONS = {
    'packages': ['pygame'],
}

setup(
    name='Chess 2',
    app=['game.py'],
    data_files=['chess.png'],
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
