#!/bin/bash

DISPLAY_NAME=$(xrandr | grep " connected" | awk '{print $1}' | head -1)
WANTED_RES="1920x1080"
WANTED_RATE="120"

# Nur setzen wenn aktuelle Auflösung nicht stimmt
CURRENT=$(xrandr | grep "^\s*${WANTED_RES}" | grep "\*")
if [ -z "$CURRENT" ]; then
    xrandr --output "$DISPLAY_NAME" --mode "$WANTED_RES" --rate "$WANTED_RATE"
fi
