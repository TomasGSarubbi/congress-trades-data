#!/usr/bin/env bash
# Prepara una sesion nueva para producir Shorts de Cifra Clave.
# Se puede correr todas las veces que haga falta: solo instala o descarga lo que falta.
#   bash setup.sh
# Los modelos de voz quedan en $CIFRA_MODELS (por defecto ~/.cache/cifra-clave/kokoro).
set -uo pipefail
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODELS="${CIFRA_MODELS:-$HOME/.cache/cifra-clave/kokoro}"
REL="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
FAIL=0
ok()  { printf 'OK     %s\n' "$1"; }
bad() { printf 'FALTA  %s\n' "$1"; FAIL=1; }
pipi() { pip install --break-system-packages -q "$@" 2>/dev/null || pip install -q "$@"; }

command -v ffmpeg >/dev/null && ok "ffmpeg" || bad "ffmpeg"

python3 -c "import kokoro_onnx, soundfile, numpy" 2>/dev/null || pipi "kokoro-onnx==0.6.1" soundfile || pipi kokoro-onnx soundfile
python3 -c "import kokoro_onnx, soundfile, numpy" 2>/dev/null && ok "voz: kokoro-onnx + soundfile" || bad "kokoro-onnx / soundfile"

python3 -c "import playwright" 2>/dev/null || pipi playwright
python3 -c "import playwright" 2>/dev/null && ok "playwright" || bad "playwright"

# Modelos de voz: se descargan una vez y se comprueba que el archivo sea exactamente el esperado.
mkdir -p "$MODELS"
get() {  # nombre  sha256
  local f="$MODELS/$1"
  if [ ! -s "$f" ] || ! echo "$2  $f" | sha256sum -c --status 2>/dev/null; then
    curl -fL --retry 3 --retry-delay 2 -sS -o "$f.part" "$REL/$1" && mv "$f.part" "$f"
  fi
  echo "$2  $f" | sha256sum -c --status 2>/dev/null && ok "modelo $1" || bad "modelo $1 (descarga incompleta o distinta de la esperada)"
}
get kokoro-v1.0.onnx 7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5
get voices-v1.0.bin  bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d

# Fuentes: si el sistema no trae Anton e Inter, se instalan las del kit.
have_fonts() { local L; L="$(fc-list 2>/dev/null)"; grep -q "Anton" <<<"$L" && grep -qE "Inter[,:]" <<<"$L"; }
if ! have_fonts; then
  mkdir -p "$HOME/.local/share/fonts/cifra-clave"
  cp "$KIT"/fonts/*.ttf "$KIT"/fonts/*.otf "$HOME/.local/share/fonts/cifra-clave/" 2>/dev/null
  fc-cache -f 2>/dev/null
fi
have_fonts && ok "fuentes Anton + Inter" || bad "fuentes Anton / Inter"

# Navegador para filmar: Chrome del sistema o, si no hay, el Chromium de Playwright.
python3 - <<'PY' 2>/dev/null && ok "Chrome para filmar" || bad "Chrome / Chromium (probar: python3 -m playwright install chromium)"
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    a = ["--no-sandbox"]
    try: b = p.chromium.launch(channel="chrome", headless=True, args=a)
    except Exception: b = p.chromium.launch(headless=True, args=a)
    b.close()
PY

echo "MODELOS=$MODELS"
if [ "$FAIL" = 0 ]; then echo "LISTO: entorno preparado"; else echo "HAY FALTANTES: revisar las lineas FALTA"; exit 1; fi
