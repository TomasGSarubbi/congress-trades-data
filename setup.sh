#!/usr/bin/env bash
# Prepara una sesion nueva para producir Shorts de Cifra Clave.
# Se puede correr todas las veces que haga falta: solo instala o descarga lo que falta.
#   bash setup.sh
# Los modelos quedan en $CIFRA_CACHE (por defecto ~/.cache/cifra-clave):
#   supertonic/  la voz del canal          oido/  Whisper, que controla la pronunciacion
#   kokoro/      la voz de los primeros videos (solo hace falta para rehacerlos)
set -uo pipefail
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE="${CIFRA_CACHE:-$HOME/.cache/cifra-clave}"
MODELS="${CIFRA_MODELS:-$CACHE/kokoro}"
REL="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
SHERPA="https://github.com/k2-fsa/sherpa-onnx/releases/download"
FAIL=0
ok()  { printf 'OK     %s\n' "$1"; }
bad() { printf 'FALTA  %s\n' "$1"; FAIL=1; }
opc() { printf 'AVISO  %s\n' "$1"; }
pipi() { pip install --break-system-packages -q "$@" 2>/dev/null || pip install -q "$@"; }

command -v ffmpeg >/dev/null && ok "ffmpeg" || bad "ffmpeg"

python3 -c "import sherpa_onnx, num2words, soundfile, numpy" 2>/dev/null || pipi "sherpa-onnx==2.0.3" num2words soundfile || pipi sherpa-onnx num2words soundfile
python3 -c "import sherpa_onnx, num2words, soundfile, numpy" 2>/dev/null && ok "voz y oido: sherpa-onnx + num2words + soundfile" || bad "sherpa-onnx / num2words / soundfile"

python3 -c "import kokoro_onnx" 2>/dev/null || pipi "kokoro-onnx==0.6.1" || pipi kokoro-onnx
python3 -c "import kokoro_onnx" 2>/dev/null && ok "voz anterior: kokoro-onnx" || opc "kokoro-onnx no se instalo (solo hace falta para rehacer videos con la voz anterior)"

python3 -c "import playwright" 2>/dev/null || pipi playwright
python3 -c "import playwright" 2>/dev/null && ok "playwright" || bad "playwright"

# Modelos: se descargan una vez y se comprueba que el archivo sea exactamente el esperado.
# Los que vienen en .tar.bz2 se comprueban antes de abrirlos.
gettar() {  # carpeta  nombre  sha256  url  archivo_testigo
  local dir="$CACHE/$1" name="$2" sha="$3" tar="$CACHE/$1/$2.tar.bz2"
  mkdir -p "$dir"
  if [ ! -s "$dir/$name/$5" ] || [ ! -f "$dir/$name/.ok-$sha" ]; then
    if [ ! -s "$tar" ] || ! echo "$sha  $tar" | sha256sum -c --status 2>/dev/null; then
      curl -fL --retry 3 --retry-delay 2 -sS -o "$tar.part" "$4/$name.tar.bz2" && mv "$tar.part" "$tar"
    fi
    echo "$sha  $tar" | sha256sum -c --status 2>/dev/null && tar -xjf "$tar" -C "$dir" --no-same-owner && touch "$dir/$name/.ok-$sha"
  fi
  [ -s "$dir/$name/$5" ] && [ -f "$dir/$name/.ok-$sha" ] && ok "modelo $name" || bad "modelo $name (descarga incompleta o distinta de la esperada)"
}
gettar supertonic sherpa-onnx-supertonic-3-tts-int8-2026-05-11 82fa96f91c4ef8abaae3a14a3f4153facf88bed821d1f7331cec2700f432c427 "$SHERPA/tts-models" vector_estimator.int8.onnx
gettar oido       sherpa-onnx-whisper-turbo                    b11acbbcd660b44a8e0df33724feb5aaa709cf65668f2823d59f656312544f22 "$SHERPA/asr-models" turbo-encoder.int8.onnx

mkdir -p "$MODELS"
get() {  # nombre  sha256   (voz anterior: si falla no frena la corrida)
  local f="$MODELS/$1"
  if [ ! -s "$f" ] || ! echo "$2  $f" | sha256sum -c --status 2>/dev/null; then
    curl -fL --retry 3 --retry-delay 2 -sS -o "$f.part" "$REL/$1" && mv "$f.part" "$f"
  fi
  echo "$2  $f" | sha256sum -c --status 2>/dev/null && ok "modelo $1 (voz anterior)" || opc "modelo $1 no se descargo (solo hace falta para rehacer videos con la voz anterior)"
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

echo "MODELOS=$CACHE"
if [ "$FAIL" = 0 ]; then echo "LISTO: entorno preparado"; else echo "HAY FALTANTES: revisar las lineas FALTA"; exit 1; fi
