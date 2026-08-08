run() { S=$(printf '%s' "$1" | base64); ssh contabo-vps "/home/opc/reseau/query.py read \"\$(echo $S | base64 -d)\"" 2>&1; }
