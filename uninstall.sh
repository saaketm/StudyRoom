#!/bin/bash
# Removes ONLY what install.sh added (launcher, icon, top-bar indicator, taskbar pin).
# Your study data in ~/.local/share/ypt-study/ is NOT touched.
set -euo pipefail
APP_ID="io.github.studyroom.Studyroom"
EXT_UUID="studyroom-timer@studyroom.local"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"

echo "This will remove:"
echo "  $DATA/applications/$APP_ID.desktop"
echo "  $DATA/icons/hicolor/scalable/apps/$APP_ID.svg"
echo "  $DATA/gnome-shell/extensions/$EXT_UUID/  (3 files)"
echo "  the StudyRoom pin on your taskbar"
echo "Your data folder $DATA/ypt-study/ will be kept."
read -r -p "Continue? [y/N] " ans
[[ "$ans" == "y" || "$ans" == "Y" ]] || { echo "Nothing changed."; exit 0; }

gnome-extensions disable "$EXT_UUID" 2>/dev/null || true
rm -f "$DATA/applications/$APP_ID.desktop" "$DATA/icons/hicolor/scalable/apps/$APP_ID.svg"
rm -f "$DATA/gnome-shell/extensions/$EXT_UUID/"{metadata.json,extension.js,stylesheet.css}
rmdir "$DATA/gnome-shell/extensions/$EXT_UUID" 2>/dev/null || true
FAVS="$(gsettings get org.gnome.shell favorite-apps)"
NEW="$(python3 -c 'import ast,sys; f=ast.literal_eval(sys.argv[1]); print(str([x for x in f if x != sys.argv[2]]))' "$FAVS" "$APP_ID.desktop")"
gsettings set org.gnome.shell favorite-apps "$NEW"
echo "Done."
