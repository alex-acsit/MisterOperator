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
        quick=0
        while true; do
            started=$(date +%s)
            python3 "$DIR/arcadekiosk.py" >>/tmp/arcadekiosk.log 2>&1
            code=$?
            # Each restart makes the MiSTer re-open every controller, so a kiosk
            # that keeps crashing would leave the controls dead. Back off.
            if [ $(( $(date +%s) - started )) -lt 20 ]; then quick=$((quick + 1)); else quick=0; fi
            if [ $quick -ge 3 ]; then
                echo "$(date +%T) kiosk exited ($code) $quick times quickly; waiting 60 s" >>/tmp/arcadekiosk.log
                sleep 60
            else
                echo "$(date +%T) kiosk exited ($code), restarting" >>/tmp/arcadekiosk.log
                sleep 2
            fi
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
