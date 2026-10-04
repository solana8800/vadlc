#!/usr/bin/env bash
# Build, optimize and package v-adlc-agent-server for GitHub Release.
#
# Usage:
#   bash scripts/release-agent-server.sh [--version <ver>] [--publish] [--out-dir <dir>]
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VADLC_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CODEX_RS="$VADLC_ROOT/codex-rs"

VERSION="0.2.33"
PUBLISH=0
OUT_DIR="$VADLC_ROOT/dist/releases"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      VERSION="$2"
      shift 2
      ;;
    --publish)
      PUBLISH=1
      shift
      ;;
    --out-dir)
      OUT_DIR="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

# Detect platform and architecture
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"

case "$OS" in
  darwin)
    if [[ "$ARCH" != "arm64" ]]; then
      echo "Error: Only Apple Silicon (arm64) is supported on macOS." >&2
      exit 1
    fi
    PLATFORM_KEY="darwin-arm64"
    ARCHIVE_EXT="tar.gz"
    BINARY_NAME="v-adlc-agent-server"
    ;;
  linux)
    if [[ "$ARCH" != "x86_64" ]]; then
      echo "Error: Only x86_64 is supported on Linux." >&2
      exit 1
    fi
    PLATFORM_KEY="linux-x64"
    ARCHIVE_EXT="tar.gz"
    BINARY_NAME="v-adlc-agent-server"
    ;;
  msys*|mingw*|cygwin*)
    PLATFORM_KEY="win32-x64"
    ARCHIVE_EXT="zip"
    BINARY_NAME="v-adlc-agent-server.exe"
    ;;
  *)
    echo "Unsupported OS: $OS" >&2
    exit 1
    ;;
esac

echo "=================================================="
echo "==> Building v-adlc-agent-server $VERSION ($PLATFORM_KEY)"
echo "=================================================="

cd "$CODEX_RS"
cargo build -p codex-app-server --bin v-adlc-agent-server --release

BUILT_BINARY="$CODEX_RS/target/release/$BINARY_NAME"
if [[ ! -f "$BUILT_BINARY" ]]; then
  echo "Error: Binary not found at $BUILT_BINARY" >&2
  exit 1
fi

# Strip symbols
echo "==> Stripping binary symbols"
if [[ "$OS" == "darwin" ]]; then
  strip -S "$BUILT_BINARY" || true
elif [[ "$OS" == "linux" ]]; then
  strip --strip-all "$BUILT_BINARY" || true
fi

SIZE_MB=$(python3 -c "import os; print(f'{os.path.getsize(\"$BUILT_BINARY\") / (1024*1024):.1f}')")
echo "==> Binary size: ${SIZE_MB} MB"

STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGE_DIR"' EXIT

cp "$BUILT_BINARY" "$STAGE_DIR/$BINARY_NAME"
chmod 755 "$STAGE_DIR/$BINARY_NAME"

# Copy license & notice
for f in LICENSE NOTICE; do
  if [[ -f "$VADLC_ROOT/$f" ]]; then
    cp "$VADLC_ROOT/$f" "$STAGE_DIR/"
  else
    touch "$STAGE_DIR/$f"
  fi
done

# Create runtime-manifest.json
SOURCE_COMMIT="$(git -C "$VADLC_ROOT" rev-parse HEAD)"
SHA256_BIN=$(python3 -c "import hashlib; print(hashlib.sha256(open('$BUILT_BINARY', 'rb').read()).hexdigest())")

cat <<EOF > "$STAGE_DIR/runtime-manifest.json"
{
  "schemaVersion": 1,
  "engine": "v-adlc-agent-server",
  "version": "$VERSION",
  "sourceCommit": "$SOURCE_COMMIT",
  "protocol": "app-server-v2",
  "platforms": {
    "$PLATFORM_KEY": {
      "file": "$BINARY_NAME",
      "sha256": "$SHA256_BIN"
    }
  }
}
EOF

mkdir -p "$OUT_DIR"
ARCHIVE_NAME="v-adlc-agent-server-v${VERSION}-${PLATFORM_KEY}.${ARCHIVE_EXT}"
ARCHIVE_PATH="$OUT_DIR/$ARCHIVE_NAME"

echo "==> Creating release archive: $ARCHIVE_NAME"
if [[ "$ARCHIVE_EXT" == "tar.gz" ]]; then
  tar -czf "$ARCHIVE_PATH" -C "$STAGE_DIR" "$BINARY_NAME" runtime-manifest.json LICENSE NOTICE
else
  (cd "$STAGE_DIR" && zip -q -r "$ARCHIVE_PATH" "$BINARY_NAME" runtime-manifest.json LICENSE NOTICE)
fi

SHA256_ARCHIVE=$(python3 -c "import hashlib; print(hashlib.sha256(open('$ARCHIVE_PATH', 'rb').read()).hexdigest())")
echo "$SHA256_ARCHIVE  $ARCHIVE_NAME" > "$ARCHIVE_PATH.sha256"

ARCHIVE_MB=$(python3 -c "import os; print(f'{os.path.getsize(\"$ARCHIVE_PATH\") / (1024*1024):.1f}')")
echo "==> Archive created: $ARCHIVE_PATH (${ARCHIVE_MB} MB)"
echo "==> SHA256: $SHA256_ARCHIVE"

if [[ "$PUBLISH" -eq 1 ]]; then
  echo "==> Publishing to GitHub Releases"
  TAG="agent-server-v$VERSION"
  if gh release view "$TAG" >/dev/null 2>&1; then
    gh release upload "$TAG" "$ARCHIVE_PATH" "$ARCHIVE_PATH.sha256" --clobber
  else
    gh release create "$TAG" "$ARCHIVE_PATH" "$ARCHIVE_PATH.sha256" \
      --title "v-adlc-agent-server v$VERSION" \
      --notes "Pre-built standalone lightweight private agent server for ADLC (v$VERSION)."
  fi
  echo "==> Published successfully to $TAG!"
fi
