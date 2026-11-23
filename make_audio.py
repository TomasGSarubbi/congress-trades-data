"""Genera la narracion y los tiempos de un Short a partir de spec.json.

Uso:  python3 -I make_audio.py <spec.json> <carpeta_salida>
      (la forma anterior, con <modelo.onnx> <voices.bin> adelante, sigue funcionando)

La voz se elige en el campo "voice" del spec:
  {"name": "M1", "speed": 1.1}                          Supertonic 3: M1 a M5 (hombre), F1 a F5 (mujer)
  {"name": "em_alex", "speed": 1.0, "lang": "es-419"}   Kokoro: em_alex, em_santa, ef_dora (voz de los primeros videos)

Control automatico ("oido"): cada frase se transcribe con Whisper y se compara con el guion. Si una toma
no se entiende se genera otra (las ultimas, un poco mas despacio) y queda la mejor. Lo que no se pudo
confirmar sale como "AVISO VOZ": hay que reescribir esa frase en 'tts' y volver a correr.

Escribe en <carpeta_salida>:
  voz_raw.wav      voz tal como sale del modelo
  voz.wav          voz final: comprimida suave y normalizada a -14 LUFS
  spec.timed.json  el mismo spec con start/end por linea, por fragmento de subtitulo y por escena (30 fps)
  oido.json        que se oyo en cada frase y que toma quedo
"""
import sys, os, json, re, subprocess, unicodedata
import numpy as np, soundfile as sf

_a = sys.argv[1:]
if len(_a) == 4: kok_model, kok_voices, spec_path, outdir = _a
elif len(_a) == 2: kok_model, kok_voices, spec_path, outdir = None, None, _a[0], _a[1]
else: sys.exit(__doc__)

CACHE = os.environ.get("CIFRA_CACHE", os.path.expanduser("~/.cache/cifra-clave"))
KOKORO_DIR = os.environ.get("CIFRA_MODELS", CACHE + "/kokoro")
SUPERTONIC_DIR = CACHE + "/supertonic/sherpa-onnx-supertonic-3-tts-int8-2026-05-11"
WHISPER_DIR = CACHE + "/oido/sherpa-onnx-whisper-turbo"
VOZ_DEL_CANAL = {"name": "M1", "speed": 1.1}      # se usa si el spec no trae "voice"
FPS, LEAD, TAIL = 30, 0.20, 0.90
NIVEL = "acompressor=threshold=-21dB:ratio=2.2:attack=10:release=150:makeup=1.5,loudnorm=I=-14:TP=-1.5:LRA=11"

spec = json.load(open(spec_path, encoding="utf-8"))
V = spec.get("voice") or dict(VOZ_DEL_CANAL)
spec["voice"] = V


# ---------------------------------------------------------------- motores de voz
class Supertonic:
    """Supertonic 3 (Supertone, licencia OpenRAIL-M) mediante sherpa-onnx. 44,1 kHz.
    Lee el texto tal cual: con palabras mal escritas a proposito pronuncia peor, asi que en 'tts'
    solo se cambia la grafia de los nombres extranjeros que de verdad salen mal."""
    VOCES = ["F1", "F2", "F3", "F4", "F5", "M1", "M2", "M3", "M4", "M5"]
    TOMAS = (1.0, 1.0, 0.94, 0.94, 0.88, 0.88)           # factor de velocidad de cada toma
    CADENA = "highpass=f=70," + NIVEL                        # sin ecualizar: la voz ya sale completa

    def __init__(self, v):
        import sherpa_onnx
        d = SUPERTONIC_DIR
        cfg = sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
            supertonic=sherpa_onnx.OfflineTtsSupertonicModelConfig(
                duration_predictor=d + "/duration_predictor.int8.onnx", text_encoder=d + "/text_encoder.int8.onnx",
                vector_estimator=d + "/vector_estimator.int8.onnx", vocoder=d + "/vocoder.int8.onnx",
                tts_json=d + "/tts.json", unicode_indexer=d + "/unicode_indexer.bin", voice_style=d + "/voice.bin"),
            num_threads=2, provider="cpu"))
        if not cfg.validate(): sys.exit(f"Falta el modelo de voz en {d}: correr setup.sh")
        self.sx, self.tts = sherpa_onnx, sherpa_onnx.OfflineTts(cfg)
        self.sid, self.speed = self.VOCES.index(v["name"]), float(v.get("speed", 1.1))
        self.steps = int(v.get("steps", 8))

    def decir(self, texto, toma=0):
        g = self.sx.GenerationConfig()
        g.sid, g.num_steps, g.speed = self.sid, self.steps, self.speed * self.TOMAS[toma]
        g.extra["lang"] = "es"
        a = self.tts.generate(texto, g)
        return np.asarray(a.samples, dtype=np.float32), a.sample_rate


class Kokoro:
    """Kokoro v1.0 (Apache 2.0) mediante kokoro-onnx. 24 kHz. Voz de los videos hasta el 23/11/2026."""
    TOMAS = (1.0, 0.97, 1.03)
    # Cadena "voz calida": quita graves inutiles, sube cuerpo, baja brillo.
    CADENA = "highpass=f=70,bass=g=2.5:f=150:w=0.8,treble=g=-2.5:f=6000:w=0.7," + NIVEL

    def __init__(self, v):
        from kokoro_onnx import Kokoro as K
        self.k = K(kok_model or KOKORO_DIR + "/kokoro-v1.0.onnx", kok_voices or KOKORO_DIR + "/voices-v1.0.bin")
        self.voice, self.speed, self.lang = v.get("name", "em_alex"), float(v.get("speed", 1.0)), v.get("lang", "es-419")

    def decir(self, texto, toma=0):
        s, sr = self.k.create(texto, voice=self.voice, speed=self.speed * self.TOMAS[toma], lang=self.lang)
        return np.asarray(s, dtype=np.float32), sr


motor = Supertonic(V) if V.get("name") in Supertonic.VOCES else Kokoro(V)


def toma(texto, k=0):
    """Una toma de la frase, sin el silencio de las puntas."""
    s, sr = motor.decir(texto, k)
    thr = 0.02 * float(np.abs(s).max()); idx = np.where(np.abs(s) > thr)[0]
    return s[max(0, idx[0] - int(0.03 * sr)): min(len(s), idx[-1] + int(0.06 * sr))], sr


# ---------------------------------------------------------------- oido automatico
def _letras(n):
    try:
        from num2words import num2words
        return num2words(int(n), lang="es")
    except Exception:
        return n


def palabras(t):
    """Texto -> palabras comparables: minusculas, sin tildes ni signos, cifras y simbolos en letras."""
    t = t.lower().replace("*", "").replace("s&p", "s y p").replace("&", " y ")
    t = re.sub(r"(?:usd|us\$|\$)\s*([\d.,]+)", r"\1 dolares", t).replace("%", " por ciento ")
    for _ in range(3): t = re.sub(r"(\d)[.,](\d{3})(?!\d)", r"\1\2", t)                  # 36.000 -> 36000
    t = re.sub(r"(\d+)[.,](\d{1,2})(?!\d)", lambda m: f"{m.group(1)} coma {m.group(2)}", t)
    t = re.sub(r"\d+", lambda m: " " + _letras(m.group(0)) + " ", t)
    t = unicodedata.normalize("NFC", "".join(c for c in unicodedata.normalize("NFD", t)
                                             if unicodedata.category(c) != "Mn" or c == "\u0303"))
    t = re.sub(r"\b(veinti)?uno\b", lambda m: (m.group(1) or "") + "un", re.sub(r"[^a-zñ ]+", " ", t))
    return t.split()


def clave(w):
    """Clave fonetica aproximada (b=v, s=z=ce, k=c=qu, y=ll=i, sin h): 'Discóveri' y 'Discovery' coinciden."""
    w = re.sub(r"qu(?=[ei])", "k", w); w = re.sub(r"gu(?=[ei])", "g", w)
    w = re.sub(r"c(?=[ei])", "s", w); w = re.sub(r"g(?=[ei])", "j", w)
    w = w.replace("ch", "#").replace("ll", "y").replace("h", "").replace("#", "ch")
    w = w.translate(str.maketrans("vzqwx", "bskus")).replace("c", "k").replace("kh", "ch")
    return re.sub(r"(.)\1+", r"\1", re.sub(r"y\b", "i", w))


def igual(a, b):
    """Misma palabra al oido. En palabras largas se tolera una sola vocal distinta (Páramaunt / Paramount);
    una consonante distinta ya es otra palabra (bajaron / vallaron)."""
    ka, kb = clave(a), clave(b)
    if ka == kb: return True
    if len(ka) != len(kb) or len(ka) < 6: return False
    d = [(x, y) for x, y in zip(ka, kb) if x != y]
    return len(d) == 1 and d[0][0] in "aeiou" and d[0][1] in "aeiou"


RELLENO = {"dolares", "pesos", "euros", "eh"}                # palabras que el transcriptor agrega solo


def alinear(R, H):
    """Empareja guion (R) y transcripcion (H). Devuelve pasos ('ok'|'cambio'|'falta'|'sobra', i, j) en orden."""
    n, m = len(R), len(H)
    D = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1): D[i][0] = i
    for j in range(1, m + 1): D[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            D[i][j] = min(D[i - 1][j] + 1, D[i][j - 1] + 1, D[i - 1][j - 1] + (not igual(R[i - 1], H[j - 1])))
    i, j, pasos = n, m, []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and D[i][j] == D[i - 1][j - 1] + (not igual(R[i - 1], H[j - 1])):
            pasos.append(("ok" if igual(R[i - 1], H[j - 1]) else "cambio", i - 1, j - 1)); i, j = i - 1, j - 1
        elif i > 0 and D[i][j] == D[i - 1][j] + 1: pasos.append(("falta", i - 1, None)); i -= 1
        else: pasos.append(("sobra", None, j - 1)); j -= 1
    return pasos[::-1]


class Oido:
    def __init__(self):
        self.rec = None
        if V.get("check") is False or os.environ.get("CIFRA_SIN_OIDO"):
            print("OIDO: desactivado."); return
        try:
            import sherpa_onnx
            w = WHISPER_DIR
            self.rec = sherpa_onnx.OfflineRecognizer.from_whisper(
                encoder=w + "/turbo-encoder.int8.onnx", decoder=w + "/turbo-decoder.int8.onnx", tokens=w + "/turbo-tokens.txt",
                language="es", task="transcribe", num_threads=2)
        except Exception as e:                                                # sin el modelo se sigue, pero sin control
            print(f"OIDO: no disponible ({str(e)[:80]}). Correr setup.sh. Se continua SIN control de pronunciacion.")

    def oir(self, s, sr):
        st = self.rec.create_stream(); st.accept_waveform(sr, s); self.rec.decode_stream(st)
        return st.result.text.strip()


# ---------------------------------------------------------------- frases del guion
F = []                                                                        # una entrada por frase, en orden
for si, sc in enumerate(spec["scenes"]):
    for li, line in enumerate(sc["lines"]):
        visto = " ".join(c[0] if isinstance(c, list) else c for c in line["caps"])
        F.append({"si": si, "li": li, "line": line, "dicho": palabras(line["tts"]), "visto": palabras(visto)})

audio, tomas, sr = [], [0] * len(F), None
for f in F:
    s, sr = toma(f["line"]["tts"]); audio.append(s)
estado = [None] * len(F)                                                      # (lista de diferencias, lo que se oyo)
oido = Oido()


def escuchar(grupo):
    """Transcribe varias frases seguidas (el contexto ayuda) y reparte las diferencias frase por frase."""
    partes = []
    for i in grupo: partes += [audio[i], np.zeros(int(0.6 * sr), dtype=np.float32)]
    H = palabras(oido.oir(np.concatenate([np.zeros(int(0.3 * sr), dtype=np.float32)] + partes), sr))
    mejor = {}
    for ref in ("dicho", "visto"):                                            # "visto" cubre nombres escritos como suenan y cifras
        R, de = [], []
        for i in grupo: R += F[i][ref]; de += [i] * len(F[i][ref])
        dif, oyo, cur = {i: [] for i in grupo}, {i: [] for i in grupo}, grupo[0]
        for tipo, ri, hj in alinear(R, H):
            if ri is not None: cur = de[ri]
            if hj is not None: oyo[cur].append(H[hj])
            if tipo == "cambio": dif[cur].append(f"«{R[ri]}» se oyó «{H[hj]}»")
            elif tipo == "falta": dif[cur].append(f"no se oyó «{R[ri]}»")
            elif tipo == "sobra" and H[hj] not in RELLENO: dif[cur].append(f"se oyó de más «{H[hj]}»")
        for i in grupo:
            if i not in mejor or len(dif[i]) < len(mejor[i][0]): mejor[i] = (dif[i], " ".join(oyo[i]))
    return mejor


if oido.rec:
    try:
        grupos, g, dur = [], [], 0.0                                          # tandas de hasta ~22 s
        for i in range(len(F)):
            d = len(audio[i]) / sr + 0.6
            if g and dur + d > 22: grupos.append(g); g, dur = [], 0.0
            g.append(i); dur += d
        if g: grupos.append(g)
        for g in grupos:
            for i, r in escuchar(g).items(): estado[i] = r
        for i in range(len(F)):                                               # otra toma para lo que no se entendio
            k = 0
            while estado[i][0] and k + 1 < len(motor.TOMAS):
                k += 1
                previa = audio[i]; audio[i], _ = toma(F[i]["line"]["tts"], k)
                r = escuchar([j for j in (i - 1, i, i + 1) if 0 <= j < len(F)])[i]
                if len(r[0]) < len(estado[i][0]): estado[i], tomas[i] = r, k
                else: audio[i] = previa
    except Exception as e:
        print(f"OIDO: fallo ({str(e)[:120]}). Se continua SIN control de pronunciacion.")
        estado = [None] * len(F)


# ---------------------------------------------------------------- tiempos y armado
def weight(s):
    s = re.sub(r"[*¿¡]", "", s).strip()
    return len(s) + (4 if s.endswith(",") else 0) + (6 if s.endswith((".", ":", "?", "!")) else 0)


def loudness(path):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    summ = err[err.rfind("Summary:"):]
    return float(re.search(r"I:\s+(-?[\d.]+) LUFS", summ).group(1)), float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", summ).group(1))


parts = [np.zeros(int(LEAD * sr), dtype=np.float32)]
t, informe = LEAD, []
for n, f in enumerate(F):
    si, li, line, s = f["si"], f["li"], f["line"], audio[n]
    last = li == len(spec["scenes"][si]["lines"]) - 1
    gap = float(line.get("gap", 0.30 if last else 0.45))
    d = len(s) / sr
    caps = [c if isinstance(c, list) else [c, c] for c in line["caps"]]      # [texto en pantalla, texto hablado]
    ws = [weight(sp) for _, sp in caps]; tot = sum(ws); c0 = t; timed = []
    for (disp, _), w in zip(caps, ws):
        c1 = c0 + d * w / tot
        timed.append({"text": disp, "start": round(c0, 3), "end": round(c1, 3)}); c0 = c1
    tts = line["tts"]
    line.update({"start": round(t, 3), "end": round(t + d, 3), "caps": timed})
    parts += [s, np.zeros(int(gap * sr), dtype=np.float32)]
    e = estado[n]
    marca = "sin control" if e is None else ("oido OK" if not e[0] else "AVISO VOZ") + (f" (toma {tomas[n] + 1})" if tomas[n] else "")
    print(f"escena {si+1} linea {li+1}: {d:5.2f}s inicio {t:6.2f} | {marca:18s} | {tts[:58]}")
    informe.append({"escena": si + 1, "linea": li + 1, "tts": tts, "oido": None if e is None else e[1],
                    "diferencias": None if e is None else e[0], "toma": tomas[n] + 1})
    t += d + gap
parts.append(np.zeros(int(max(0.0, TAIL - 0.30) * sr), dtype=np.float32))
audio_total = np.concatenate(parts)
total = len(audio_total) / sr
starts = [0] + [round((sc["lines"][0]["start"] - 0.10) * FPS) for sc in spec["scenes"][1:]]
frames_total = int(-(-total * FPS // 1))
for i, sc in enumerate(spec["scenes"]):
    sc["start"] = starts[i] / FPS
    sc["end"] = (starts[i + 1] if i + 1 < len(starts) else frames_total) / FPS
spec.update({"total": round(total, 3), "fps": FPS, "frames": starts, "frames_total": frames_total})
raw, pre, out = f"{outdir}/voz_raw.wav", f"{outdir}/voz_pre.wav", f"{outdir}/voz.wav"
sf.write(raw, audio_total, sr)
json.dump(spec, open(f"{outdir}/spec.timed.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(informe, open(f"{outdir}/oido.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("TOTAL:", round(total, 2), "s |", frames_total, "cuadros | escenas en cuadros:", starts)

subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-af", motor.CADENA, "-ar", "48000", "-ac", "2", pre], check=True)
I, P = loudness(pre)
gain = min(-14.0 - I, -1.0 - P)          # llegar a -14 LUFS sin pasar de -1 dB de pico
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", pre, "-af", f"volume={gain:.2f}dB", "-ar", "48000", "-ac", "2", out], check=True)
I2, P2 = loudness(out)
print(f"voz.wav lista: {I2:.1f} LUFS, pico {P2:.1f} dB (objetivo -14 LUFS) | voz {V.get('name')} a velocidad {V.get('speed', 1.0)}")

if any(e is not None for e in estado):
    malas = [x for x in informe if x["diferencias"]]
    print(f"OIDO: {len(informe) - len(malas)} de {len(informe)} frases confirmadas con transcripcion automatica.")
    for x in malas:
        print(f"AVISO VOZ escena {x['escena']} linea {x['linea']}: {'; '.join(x['diferencias'])} | se oyó: \"{x['oido']}\"")
    if malas:
        print("  -> Reescribir esas frases en 'tts' (otra palabra, otro orden, o unirlas con la frase vecina) y volver a correr.")
        print("     Si lo unico distinto es un nombre propio bien dicho, se puede seguir.")
