#!/bin/bash
# MisterOperator: install or update the arcade kiosk from GitHub.
# Put this in /media/fat/Scripts and run it from the MiSTer Scripts menu (or SSH).
#   - Kiosk already installed: updates it to the latest release, keeping your
#     settings (kiosk.ini), credits, play counts and box art.
#   - Not installed yet: downloads the latest release and runs its installer.

REPO="alex-acsit/MisterOperator"
DIR=/media/fat/arcade_kiosk
CACERT=/etc/ssl/certs/cacert.pem

if [ -f "$DIR/arcadekiosk.py" ]; then
    python3 "$DIR/arcadekiosk.py" --update "$@"
    exit $?
fi

echo "Installing MisterOperator from github.com/$REPO ..."
CURL=(curl -fsSL --max-time 120 --retry 2 -H "User-Agent: MisterOperator-updater")
[ -f "$CACERT" ] && CURL+=(--cacert "$CACERT")

URL=$("${CURL[@]}" "https://api.github.com/repos/$REPO/releases/latest" | python3 -c '
import json, sys
rel = json.load(sys.stdin)
for a in rel.get("assets", []):
    n = a["name"].lower()
    if n.startswith("misteroperator") and n.endswith(".zip"):
        print(a["browser_download_url"]); break
')
if [ -z "$URL" ]; then
    echo "Couldn't find a release to download. Check the network connection,"
    echo "and that github.com/$REPO is public."
    exit 1
fi

TMP=/tmp/misteroperator_install
rm -rf "$TMP" && mkdir -p "$TMP"
echo "Downloading $URL"
"${CURL[@]}" -o "$TMP/release.zip" "$URL" || { echo "Download failed."; exit 1; }
python3 -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" \
    "$TMP/release.zip" /media/fat || { echo "Couldn't unpack the download."; exit 1; }
rm -rf "$TMP"
bash /media/fat/Scripts/install_arcade_kiosk.sh
