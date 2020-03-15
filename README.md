# Chess 2

Chess 2 is a multi-player real time strategy game based on the classic game of Chess.

# Develop/build

## macOS

    python setup.py py2app
    # Remove unneeded resources to save some space
    rm dist/Chess\ 2.app/Contents/Frameworks/lib*.dylib
    rm -rf dist/Chess\ 2.app/Contents/Resources/lib/{tcl,tk}*
    rm -r dist/Chess\ 2.app/Contents/Resources/lib/python3.8/pygame/{docs,examples,tests}

(this worked for me on macOS 10.14.6 with Python 3.8.2 and pygame 2.0.0.dev6)
