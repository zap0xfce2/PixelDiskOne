#!/bin/bash

PLAYER1_MAC="e4:17:d8:96:66:69"
PLAYER2_MAC="e4:17:d8:ae:66:69"

find_index_by_mac() {
    local target="$1"
    for js in /dev/input/js*; do
        local name
        name=$(basename "$js")
        local mac
        mac=$(cat "/sys/class/input/${name}/device/uniq" 2>/dev/null)
        if [[ "$mac" == "$target" ]]; then
            echo "${name//[!0-9]/}"
            return
        fi
    done
    echo ""
}

first_available_js_index() {
    local i=0
    while [[ -e "/dev/input/js$i" ]]; do
        ((i++))
    done
    echo "$i"
}

P1_IDX=$(find_index_by_mac "$PLAYER1_MAC")
[[ -z "$P1_IDX" ]] && P1_IDX=$(first_available_js_index)

P2_IDX=$(find_index_by_mac "$PLAYER2_MAC")
if [[ -z "$P2_IDX" ]]; then
    NEXT=$((P1_IDX + 1))
    while [[ -e "/dev/input/js$NEXT" ]]; do ((NEXT++)); done
    P2_IDX="$NEXT"
fi

exec retroarch \
    -d "1:$P1_IDX" \
    -d "2:$P2_IDX" \
    "$@"
