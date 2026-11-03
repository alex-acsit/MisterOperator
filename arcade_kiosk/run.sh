#!/bin/bash
# Starts the Arcade Kiosk in the background and restarts it if it ever stops.
# Called from /media/fat/linux/user-startup.sh with "start".

DIR=/media/fat/arcade_kiosk
SUPERVISOR_PID=/tmp/arcadekiosk_supervisor.pid

start() {
    if [ -f "$SUPERVISOR_PID" ] && kill -0 "$(cat $SUPERVISOR_PID)" 2>/dev/null; then
        echo "Arcade Kiosk already running"
        return
    fi
    (
        echo $BASHPID > "$SUPERVISOR_PID"
        while true; do
            python3 "$DIR/arcadekiosk.py" >>/tmp/arcadekiosk.log 2>&1
            echo "$(date +%T) kiosk exited ($?), restarting" >>/tmp/arcadekiosk.log
            sleep 2
        done
    ) </dev/null >/dev/null 2>&1 &
    echo "Arcade Kiosk started"
}

stop() {
    [ -f "$SUPERVISOR_PID" ] && kill "$(cat $SUPERVISOR_PID)" 2>/dev/null
    rm -f "$SUPERVISOR_PID"
    [ -f /tmp/arcadekiosk.pid ] && kill "$(cat /tmp/arcadekiosk.pid)" 2>/dev/null
    echo "Arcade Kiosk stopped"
}

case "$1" in
    start) start ;;
    stop) stop ;;
    restart) stop; sleep 1; start ;;
    *) echo "usage: $0 start|stop|restart" ;;
esac
