#!/usr/bin/env bash
# Build Folio.app for macOS (double-clickable GUI launcher).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('$ROOT/pyproject.toml', 'rb'))['project']['version'])")"
APP="$ROOT/dist/Folio.app"
MACOS="$APP/Contents/MacOS"
RESOURCES="$APP/Contents/Resources"

echo "Building Folio.app ($VERSION)..."
rm -rf "$APP"
mkdir -p "$MACOS" "$RESOURCES"

sed "s|@FOLIO_PROJECT_DIR@|$ROOT|g" "$ROOT/scripts/macos/launcher.sh" > "$MACOS/Folio"
chmod +x "$MACOS/Folio"

sed "s|@FOLIO_VERSION@|$VERSION|g" "$ROOT/scripts/macos/Info.plist" > "$APP/Contents/Info.plist"

if [[ -f "$ROOT/scripts/macos/Folio.icns" ]]; then
	cp "$ROOT/scripts/macos/Folio.icns" "$RESOURCES/Folio.icns"
else
	/usr/bin/sips -s format png -z 512 512 /System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/GenericApplicationIcon.icns --out "$RESOURCES/icon.png" >/dev/null 2>&1 || true
	if [[ -f "$RESOURCES/icon.png" ]]; then
		mkdir -p "$RESOURCES/Folio.iconset"
		for size in 16 32 128 256 512; do
			double=$((size * 2))
			sips -z "$size" "$size" "$RESOURCES/icon.png" --out "$RESOURCES/Folio.iconset/icon_${size}x${size}.png" >/dev/null
			sips -z "$double" "$double" "$RESOURCES/icon.png" --out "$RESOURCES/Folio.iconset/icon_${size}x${size}@2x.png" >/dev/null
		done
		if iconutil -c icns "$RESOURCES/Folio.iconset" -o "$RESOURCES/Folio.icns" 2>/dev/null; then
			rm -rf "$RESOURCES/Folio.iconset" "$RESOURCES/icon.png"
		fi
	fi
fi

echo "Built: $APP"
echo ""
echo "Install to Applications:"
echo "  cp -R \"$APP\" /Applications/"
echo ""
echo "Or run in place:"
echo "  open \"$APP\""
