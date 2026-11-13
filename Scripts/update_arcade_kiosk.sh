#!/bin/bash
# MisterOperator: install or update the arcade kiosk from GitHub.
# Put this in /media/fat/Scripts and run it from the MiSTer Scripts menu (or SSH).
#   - Kiosk already installed: updates it to the latest release, keeping your
#     settings (kiosk.ini), credits, play counts and box art.
#   - Not installed yet: downloads the latest release and runs its installer.

# Everything runs inside main(), so bash has read the whole script before it
# starts: the update replaces this very file while it runs.
main() {
    REPO="alex-acsit/MisterOperator"
    DIR=/media/fat/arcade_kiosk
    CACERT=/etc/ssl/certs/cacert.pem

    if [ -f "$DIR/arcadekiosk.py" ] && grep -q "def update_command" "$DIR/arcadekiosk.py"; then
        python3 "$DIR/arcadekiosk.py" --update "$@"
        return $?
    fi

    # Not installed yet, or a version from before the updater existed (2.0.1 and
    # earlier): fetch the latest release directly, keeping any existing settings.
    FRESH=1
    [ -f "$DIR/arcadekiosk.py" ] && FRESH=0
    if [ $FRESH = 1 ]; then
        echo "Installing MisterOperator from github.com/$REPO ..."
    else
        echo "Updating MisterOperator from github.com/$REPO ..."
    fi
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
        return 1
    fi

    TMP=/tmp/misteroperator_install
    rm -rf "$TMP" && mkdir -p "$TMP/keep"
    echo "Downloading $URL"
    "${CURL[@]}" -o "$TMP/release.zip" "$URL" || { echo "Download failed."; return 1; }
    python3 -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).testzip()" "$TMP/release.zip" \
        || { echo "The download is damaged; nothing changed."; return 1; }

    # keep the operator's settings and data
    for f in kiosk.ini state.json games_cache.json; do
        [ -f "$DIR/$f" ] && cp "$DIR/$f" "$TMP/keep/"
    done

    python3 -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" \
        "$TMP/release.zip" /media/fat || { echo "Couldn't unpack the download."; return 1; }
    chmod +x "$DIR"/*.sh "$DIR/arcadekiosk.py" "$DIR/MiSTer_kiosk" /media/fat/Scripts/*_arcade_kiosk.sh 2>/dev/null

    for f in state.json games_cache.json; do
        [ -f "$TMP/keep/$f" ] && cp "$TMP/keep/$f" "$DIR/$f"
    done
    if [ -f "$TMP/keep/kiosk.ini" ]; then
        # the new kiosk.ini, carrying over every value that was set before
        python3 - "$DIR" "$TMP/keep/kiosk.ini" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import arcadekiosk as K
new = open(sys.argv[1] + "/kiosk.ini").read()
old = open(sys.argv[2]).read()
open(sys.argv[1] + "/kiosk.ini", "w").write(K.merge_ini(new, old))
PY
    fi
    rm -rf "$TMP"
    sync

    if [ $FRESH = 1 ]; then
        bash /media/fat/Scripts/install_arcade_kiosk.sh
    else
        echo "Updated. Restarting the kiosk..."
        "$DIR/run.sh" restart
    fi
}

main "$@"
exit $?
