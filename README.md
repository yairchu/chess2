# Chess 2

Chess 2 is a multi-player real time strategy game based on the classic game of Chess.

## Installing

### macOS

Download the app from the [releases page](https://github.com/yairchu/chess2/releases)

### Other platforms

* Install Python (version 3)
* In your terminal:
* `pip install pygame`
* `pip install pystun3`
* `python main.py`

## Playing

Chess 2 is played vs friends over the network.

* Both players need to open the game
* At the top of each player an address such as "BASK DAWN ALAN" will appear
* Such an address can be sent over to the other player via any chat platform
* The other player should type the address to connect

## Developing/building

### macOS

    python setup.py py2app
    # Remove unneeded resources to save some space
    rm dist/Chess\ 2.app/Contents/Frameworks/lib*.dylib
    rm -rf dist/Chess\ 2.app/Contents/Resources/lib/{tcl,tk}*
    rm -r dist/Chess\ 2.app/Contents/Resources/lib/python3.8/pygame/{docs,examples,tests}

(this worked for me on macOS 10.14.6 with Python 3.8.2 and pygame 2.0.0.dev6)

### Windows

    pip install pyinstaller
    pyinstaller -F main.y
    copy chess.png dist

