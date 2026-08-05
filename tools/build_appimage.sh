#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$ROOT/.build"
UPSTREAM="$WORK/DepotDownloader"
PYDIST="$WORK/py-dist"
APPDIR="$WORK/Steam_Library_Downloader.AppDir"
OUT="$ROOT/dist"
TAG="DepotDownloader_3.4.0"

rm -rf "$WORK" "$OUT"
mkdir -p "$WORK" "$OUT"

git clone --depth 1 --branch "$TAG" https://github.com/SteamRE/DepotDownloader.git "$UPSTREAM"
python3 "$ROOT/tools/patch_depotdownloader.py" "$UPSTREAM"

dotnet publish "$UPSTREAM/DepotDownloader/DepotDownloader.csproj" \
  -c Release -r linux-x64 --self-contained true \
  -p:PublishSingleFile=false -p:DebugType=None \
  -o "$WORK/backend"

python3 -m pip install --upgrade pyinstaller qrcode
python3 -m PyInstaller \
  --noconfirm --clean --windowed --onedir \
  --name SteamLibraryDownloader \
  --paths "$ROOT/src" \
  "$ROOT/src/steam_library_downloader/__main__.py" \
  --distpath "$PYDIST" --workpath "$WORK/pyinstaller" --specpath "$WORK"

mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/lib/steam-library-downloader" \
  "$APPDIR/usr/share/applications" \
  "$APPDIR/usr/share/icons/hicolor/scalable/apps" \
  "$APPDIR/usr/share/icons/hicolor/256x256/apps" \
  "$APPDIR/usr/share/icons/hicolor/512x512/apps"
cp -a "$PYDIST/SteamLibraryDownloader/." "$APPDIR/usr/lib/steam-library-downloader/"
mkdir -p "$APPDIR/usr/lib/steam-library-downloader/libexec/depotdownloader"
cp -a "$WORK/backend/." "$APPDIR/usr/lib/steam-library-downloader/libexec/depotdownloader/"
chmod +x "$APPDIR/usr/lib/steam-library-downloader/SteamLibraryDownloader" \
  "$APPDIR/usr/lib/steam-library-downloader/libexec/depotdownloader/DepotDownloader"
ln -s ../lib/steam-library-downloader/SteamLibraryDownloader "$APPDIR/usr/bin/steam-library-downloader"
cp "$ROOT/assets/dev.alastorkaneki.steamlibrarydownloader.desktop" "$APPDIR/usr/share/applications/"
cp "$ROOT/assets/dev.alastorkaneki.steamlibrarydownloader.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/"
rsvg-convert -w 256 -h 256 "$ROOT/assets/dev.alastorkaneki.steamlibrarydownloader.svg" \
  -o "$APPDIR/usr/share/icons/hicolor/256x256/apps/dev.alastorkaneki.steamlibrarydownloader.png"
rsvg-convert -w 512 -h 512 "$ROOT/assets/dev.alastorkaneki.steamlibrarydownloader.svg" \
  -o "$APPDIR/usr/share/icons/hicolor/512x512/apps/dev.alastorkaneki.steamlibrarydownloader.png"
cp "$ROOT/assets/dev.alastorkaneki.steamlibrarydownloader.desktop" "$APPDIR/"
cp "$ROOT/assets/dev.alastorkaneki.steamlibrarydownloader.svg" "$APPDIR/"
ln -s dev.alastorkaneki.steamlibrarydownloader.svg "$APPDIR/.DirIcon"
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/steam-library-downloader/SteamLibraryDownloader" "$@"
EOF
chmod +x "$APPDIR/AppRun"

APPIMAGETOOL="$WORK/appimagetool"
curl -L --fail --retry 3 \
  https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage \
  -o "$APPIMAGETOOL"
chmod +x "$APPIMAGETOOL"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGETOOL" "$APPDIR" "$OUT/Steam-Library-Downloader-0.1.0-x86_64.AppImage"
sha256sum "$OUT"/* > "$OUT/SHA256SUMS.txt"
