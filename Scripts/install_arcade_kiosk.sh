#!/bin/bash
# Arcade Kiosk installer for MiSTer.
# Copy the arcade_kiosk folder to /media/fat/arcade_kiosk, put this script in
# /media/fat/Scripts, then run it from the MiSTer Scripts menu (or over SSH).

DIR=/media/fat/arcade_kiosk
STARTUP=/media/fat/linux/user-startup.sh
MARK="# Arcade Kiosk"

if [ ! -f "$DIR/arcadekiosk.py" ]; then
    echo "Can't find $DIR/arcadekiosk.py"
    echo "Copy the arcade_kiosk folder to the root of the SD card first."
    exit 1
fi
if ! command -v python3 >/dev/null; then
    echo "python3 not found - update the MiSTer (update_all / downloader) first."
    exit 1
fi

chmod +x "$DIR/run.sh" "$DIR/arcadekiosk.py"
mkdir -p "$DIR/art"

if [ ! -f "$STARTUP" ]; then
    if [ -f /media/fat/linux/_user-startup.sh ]; then
        cp /media/fat/linux/_user-startup.sh "$STARTUP"
    else
        echo '#!/bin/sh' > "$STARTUP"
    fi
fi
if ! grep -q "$MARK" "$STARTUP"; then
    printf '\n%s\n[ -x %s/run.sh ] && %s/run.sh $1\n' "$MARK" "$DIR" "$DIR" >> "$STARTUP"
    echo "Added the kiosk to $STARTUP"
else
    echo "Kiosk already in $STARTUP"
fi

echo
echo "Next:"
echo " 1. Add the lines from MiSTer_ini_additions.txt to /media/fat/MiSTer.ini"
echo " 2. Reboot. The game list appears and asks for the PLAYER MENU"
echo "    button, then the OPERATOR button."
echo " 3. Hold OPERATOR for 1.5 s to unlock (stock menu) or lock again."
echo
echo "Log: /tmp/arcadekiosk.log"
