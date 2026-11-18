#!/bin/bash
# Installs StudyRoom for the current user only. No sudo, no system files, nothing deleted.
# What it does:
#   1. writes a launcher:  ~/.local/share/applications/io.github.studyroom.Studyroom.desktop
#   2. copies the icon:    ~/.local/share/icons/hicolor/scalable/apps/io.github.studyroom.Studyroom.svg
#   3. copies the (optional) top-bar indicator to ~/.local/share/gnome-shell/extensions/studyroom-timer@studyroom.local/
#   4. appends StudyRoom to the dock/taskbar favourites (existing favourites are kept as they are)
# The app itself keeps running from this project folder; your data lives in ~/.local/share/ypt-study/.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ID="io.github.studyroom.Studyroom"
EXT_UUID="studyroom-timer@studyroom.local"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"

chmod +x "$HERE/bin/studyroom"

mkdir -p "$DATA/applications" "$DATA/icons/hicolor/scalable/apps"
cat > "$DATA/applications/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=StudyRoom
GenericName=Study timer and deadlines
Comment=Study timer, subjects, history and deadline tracker
Exec="$HERE/bin/studyroom"
Icon=$APP_ID
Terminal=false
Categories=Education;
Keywords=study;timer;ypt;deadline;todo;calendar;
StartupNotify=true
StartupWMClass=$APP_ID
DBusActivatable=false
EOF
cp "$HERE/data/$APP_ID.svg" "$DATA/icons/hicolor/scalable/apps/$APP_ID.svg"
command -v update-desktop-database >/dev/null && update-desktop-database "$DATA/applications" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "$DATA/icons/hicolor" 2>/dev/null || true
echo "✓ Launcher installed (search for “StudyRoom” in Activities)"

EXT_DIR="$DATA/gnome-shell/extensions/$EXT_UUID"
mkdir -p "$EXT_DIR"
cp "$HERE/extension/$EXT_UUID/"{metadata.json,extension.js,stylesheet.css} "$EXT_DIR/"
echo "✓ Top-bar indicator copied (turn it on in StudyRoom → Settings → Top bar; needs one log out/in)"

if command -v gsettings >/dev/null; then
  FAVS="$(gsettings get org.gnome.shell favorite-apps)"
  if [[ "$FAVS" != *"$APP_ID.desktop"* ]]; then
    NEW="$(python3 -c 'import ast,sys; f=ast.literal_eval(sys.argv[1]); f.append(sys.argv[2]); print(str(f))' "$FAVS" "$APP_ID.desktop")"
    gsettings set org.gnome.shell favorite-apps "$NEW"
    echo "✓ Pinned to your taskbar"
  else
    echo "✓ Already pinned to your taskbar"
  fi
fi
