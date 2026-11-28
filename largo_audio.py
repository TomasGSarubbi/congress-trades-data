"""Narracion y tiempos para los videos largos de Cifra Clave (formato horizontal).

Uso:
  python3 -I largo_audio.py <spec.json> <carpeta_de_trabajo> [--voz M1] [--vel 1.0] [--pasos 16]
  python3 -I largo_audio.py <spec.json> <carpeta_de_trabajo> --externo <carpeta_con_l01.mp3_l02.mp3_...>

Escribe <carpeta>/voz.wav (-14 LUFS) y <carpeta>/spec.timed.json (tiempos de escenas, frases, subtitulos y pies).

El guion va en "narr": una lista de frases por escena. Dentro de una frase:
  {1899|mil ochocientos noventa y nueve}   se muestra lo de la izquierda y la voz dice lo de la derecha
  *texto*                                  se resalta en el subtitulo
Cada escena se narra de corrido (suena mas fluido que frase por frase) y despues se ubica cada frase
dentro del audio buscando sus pausas. Cada toma se transcribe para comprobar que dice lo que dice el guion.
"""
import sys, os, re, json, subprocess, unicodedata, difflib
import numpy as np, soundfile as sf

CACHE = os.path.expanduser("~/.cache/cifra-clave")
SUP = CACHE + "/supertonic/sherpa-onnx-supertonic-3-tts-int8-2026-05-11"
WHI = CACHE + "/oido/sherpa-onnx-whisper-turbo"
NIVEL = "highpass=f=70,acompressor=threshold=-21dB:ratio=2.2:attack=10:release=150:makeup=1.5,loudnorm=I=-14:TP=-1.5:LRA=11"
VOCES = ["F1", "F2", "F3", "F4", "F5", "M1", "M2", "M3", "M4", "M5"]
SR = 44100

args = sys.argv[1:]
def opt(name, default=None):
    if name in args:
        i = args.index(name); v = args[i + 1]; del args[i:i + 2]; return v
    return default
VOZ, VEL, PASOS, EXTERNO = opt("--voz", "M1"), float(opt("--vel", "1.0")), int(opt("--pasos", "16")), opt("--externo")
SPEC, WORK = args[0], args[1]
os.makedirs(WORK, exist_ok=True)
spec = json.load(open(SPEC, encoding="utf-8"))

# ------------------------------------------------------------------ guion -> fichas
TOK = re.compile(r"\{([^{}|]*)\|([^{}]*)\}([^\s*{}]*)|([^\s*{}]+)|(\*)")
def fichas(frase):
    """Lista de fichas {d: lo que se muestra, s: lo que se dice, hl: resaltado}."""
    out, hl = [], False
    for m in TOK.finditer(frase):
        if m.group(5): hl = not hl; continue
        if m.group(4) is not None: d = s = m.group(4)
        else: d, s = m.group(1) + m.group(3), m.group(2) + m.group(3)
        if out and re.fullmatch(r"[,.;:!?…]+", d): out[-1]["d"] += d; out[-1]["s"] += s; continue   # signo suelto tras un resaltado
        out.append({"d": d, "s": s, "hl": hl})
    return out
def peso(f):
    return len(re.sub(r"[^0-9a-záéíóúüñ]", "", f["s"].lower())) + (3 if f["s"][-1:] in ",;" else 4 if f["s"][-1:] == ":" else 0)
def dicho(fs): return " ".join(f["s"] for f in fs)
def html(fs):
    out, on = [], False
    for f in fs:
        if f["hl"] and not on: out.append("<b>" + f["d"]); on = True
        elif not f["hl"] and on: out[-1] += "</b>"; out.append(f["d"]); on = False
        else: out.append(f["d"])
    if on: out[-1] += "</b>"
    return " ".join(out)
DEBIL = set("y e o u ni que de del la el los las un una unos unas a al en por para con sin se le les lo su sus mi tu como mas más pero cuando donde hay es fue era muy ya no si".split())
def _largo(g): return sum(len(f["d"]) for f in g) + max(0, len(g) - 1)
def trozos(fs, maxc=46):
    """Parte una frase en subtitulos de hasta maxc letras: corta tras una coma si puede y nunca deja colgando una palabra debil."""
    out, i, n = [], 0, len(fs)
    while i < n:
        j = i + 1
        while j < n and _largo(fs[i:j + 1]) <= maxc: j += 1
        if j < n:
            comas = [k for k in range(i + 1, j + 1) if fs[k - 1]["d"][-1:] in ",:;?" and _largo(fs[i:k]) >= 0.5 * _largo(fs[i:j])]
            if comas: j = comas[-1]
            else:
                while j - i > 2 and re.sub(r"[^\wáéíóúñ]", "", fs[j - 1]["d"].lower()) in DEBIL: j -= 1
            if _largo(fs[j:]) < 14 and j - i > 3:                 # lo que queda es muy poco: se reparte mejor
                while j - i > 2 and _largo(fs[j:]) < 0.6 * _largo(fs[i:j]): j -= 1
                while j - i > 2 and re.sub(r"[^\wáéíóúñ]", "", fs[j - 1]["d"].lower()) in DEBIL: j -= 1
        out.append(fs[i:j]); i = j
    return out

# ------------------------------------------------------------------ oido (comprobacion por transcripcion)
import sherpa_onnx as sx
rec = sx.OfflineRecognizer.from_whisper(encoder=WHI + "/turbo-encoder.int8.onnx", decoder=WHI + "/turbo-decoder.int8.onnx",
                                        tokens=WHI + "/turbo-tokens.txt", language="es", task="transcribe", num_threads=2)
def oir(s, sr):
    z = np.zeros(int(0.3 * sr), dtype=np.float32)
    st = rec.create_stream(); st.accept_waveform(sr, np.concatenate([z, s, z])); rec.decode_stream(st)
    return st.result.text.strip()
try:
    from num2words import num2words
except ImportError:
    num2words = None
def plano(t):
    t = t.lower().replace("-", " ")
    t = re.sub(r"\$\s*(\d[\d.,]*\d|\d)", r"\1 dolares", t)          # "$2,300" -> "2,300 dolares"
    t = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", t)                   # separador de miles a la inglesa
    t = re.sub(r"(\d)\s*¢", r"\1 centavos", t)
    if num2words:
        def rep(m):
            try: return " " + num2words(int(re.sub(r"[.,]", "", m.group(0))), lang="es") + " "
            except Exception: return m.group(0)
        t = re.sub(r"\d[\d.]*\d|\d", rep, t)
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    w = re.sub(r"[^a-zñ ]+", " ", t).split()
    return ["un" if x in ("uno", "una") else x for x in w]
def parecido(ref, hyp):
    a, b = plano(ref), plano(hyp)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    dif = [(" ".join(a[i1:i2]) or "-") + " -> " + (" ".join(b[j1:j2]) or "-") for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"]
    return sm.ratio(), dif

# ------------------------------------------------------------------ voz
_tts = []
def supertonic(texto):
    if not _tts:
        _tts.append(sx.OfflineTts(sx.OfflineTtsConfig(model=sx.OfflineTtsModelConfig(supertonic=sx.OfflineTtsSupertonicModelConfig(
            duration_predictor=SUP + "/duration_predictor.int8.onnx", text_encoder=SUP + "/text_encoder.int8.onnx",
            vector_estimator=SUP + "/vector_estimator.int8.onnx", vocoder=SUP + "/vocoder.int8.onnx",
            tts_json=SUP + "/tts.json", unicode_indexer=SUP + "/unicode_indexer.bin", voice_style=SUP + "/voice.bin"), num_threads=2, provider="cpu"))))
    g = sx.GenerationConfig(); g.sid, g.num_steps, g.speed = VOCES.index(VOZ), PASOS, VEL; g.extra["lang"] = "es"
    a = _tts[0].generate(texto, g); s = np.asarray(a.samples, dtype=np.float32)
    if a.sample_rate != SR: raise SystemExit(f"frecuencia inesperada: {a.sample_rate}")
    return s
def externo(i):
    for ext in ("wav", "mp3", "m4a"):
        p = f"{EXTERNO}/l{i+1:02d}.{ext}"
        if os.path.exists(p):
            raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", p, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"], capture_output=True, check=True).stdout
            return np.frombuffer(raw, dtype=np.float32).copy()
    raise SystemExit(f"falta el audio de la escena {i+1} en {EXTERNO} (l{i+1:02d}.mp3)")
def recorta(s):
    thr = 0.02 * float(np.abs(s).max()); i = np.where(np.abs(s) > thr)[0]
    return s[max(0, i[0] - int(0.03 * SR)): min(len(s), i[-1] + int(0.08 * SR))]

def pausas(s):
    """Silencios internos de 110 ms o mas: lista de (inicio, fin) en segundos."""
    hop = int(0.01 * SR); n = len(s) // hop
    e = np.array([np.sqrt(np.mean(s[i * hop:(i + 1) * hop] ** 2) + 1e-12) for i in range(n)])
    sil = 20 * np.log10(e / e.max()) < -36
    out, run = [], 0
    for i, x in enumerate(list(sil) + [False]):
        if x: run += 1
        else:
            if run >= 11 and i - run > 5 and i < n - 5: out.append(((i - run) * 0.01, i * 0.01))
            run = 0
    return out

def ubicar(s, pesos):
    """Ubica cada frase dentro del audio de la escena. Devuelve [(t0, t1)] por frase."""
    dur = len(s) / SR; K = len(pesos) - 1
    if K == 0: return [(0.0, dur)]
    P = pausas(s); tot_sil = sum(b - a for a, b in P); habla = dur - tot_sil
    pos = []                                                   # posicion de cada pausa medida en tiempo de habla (0..1)
    acc = 0.0
    for a, b in P: pos.append((a - acc) / habla); acc += b - a
    esperado = np.cumsum(pesos)[:-1] / sum(pesos)
    INF = 1e9; n = len(P)
    if n < K:                                                  # menos pausas que cortes: reparto proporcional
        cortes = [(e * dur, e * dur) for e in esperado]
    else:
        cost = lambda j, k: abs(pos[j] - esperado[k]) * 6 - min(P[j][1] - P[j][0], 0.7)
        D = [[INF] * (n + 1) for _ in range(K + 1)]; B = [[-1] * (n + 1) for _ in range(K + 1)]
        for j in range(n + 1): D[0][j] = 0
        for k in range(1, K + 1):
            for j in range(k, n + 1):
                a = D[k][j - 1]; b = D[k - 1][j - 1] + cost(j - 1, k - 1)
                if b < a: D[k][j] = b; B[k][j] = j - 1
                else: D[k][j] = a; B[k][j] = B[k][j - 1] if j - 1 >= k else -1
        sel, j = [], n
        for k in range(K, 0, -1):
            jj = B[k][j]; sel.append(jj); j = jj
        sel.reverse(); cortes = [P[j] for j in sel]
    out, t = [], 0.0
    for a, b in cortes: out.append((t, a)); t = b
    out.append((t, dur))
    return out

# ------------------------------------------------------------------ escena por escena
lead, gap, tail = spec.get("lead", 0.5), spec.get("gap", 0.65), spec.get("tail", 2.0)
pistas, T, avisos = [], lead, []
for i, sc in enumerate(spec["scenes"]):
    F = [fichas(x) for x in sc["narr"]]
    texto = " ".join(dicho(f) for f in F)
    mejor = None
    for intento in range(1, 2 if EXTERNO else 6):
        s = recorta(externo(i) if EXTERNO else supertonic(texto))
        r, dif = parecido(texto, oir(s, SR))
        if mejor is None or r > mejor[1]: mejor = (s, r, dif, intento)
        if r >= 0.985: break
    s, r, dif, intento = mejor
    frases = ubicar(s, [sum(peso(f) for f in fs) for fs in F])
    ok_fr = []
    for (a, b), fs in zip(frases, F):                          # cada frase, escuchada por separado, tiene que coincidir
        rr, _ = parecido(dicho(fs), oir(s[int(max(0, a - 0.05) * SR): int((b + 0.08) * SR)], SR)); ok_fr.append(rr)
    if r < 0.985: avisos.append(f"escena {i+1}: la voz no dice exactamente el guion ({r:.2f}): {'; '.join(dif[:4])}")
    if min(ok_fr) < 0.8: avisos.append(f"escena {i+1}: revisar el corte entre frases ({', '.join(f'{x:.2f}' for x in ok_fr)})")
    a0 = T; a1 = T + len(s) / SR
    sent, caps = [], []
    for (a, b), fs in zip(frases, F):
        t0, t1 = a0 + a, a0 + b; sent.append({"t0": round(t0, 3), "t1": round(t1, 3)})
        G = trozos(fs); W = [sum(peso(f) for f in g) for g in G]; acc = 0
        for g, w in zip(G, W):
            c0 = t0 + (t1 - t0) * acc / sum(W); acc += w; c1 = t0 + (t1 - t0) * acc / sum(W)
            caps.append({"t0": round(c0, 3), "t1": round(c1, 3), "html": html(g)})
    for k in range(len(caps) - 1): caps[k]["t1"] = caps[k + 1]["t0"] if caps[k + 1]["t0"] - caps[k]["t1"] < 0.6 else round(caps[k]["t1"] + 0.3, 3)
    caps[-1]["t1"] = round(caps[-1]["t1"] + 0.35, 3)
    cue = {}
    for name, c in (sc.get("cues") or {}).items():
        fs = F[c["s"]]; t0, t1 = sent[c["s"]]["t0"], sent[c["s"]]["t1"]
        if c.get("end"): t = t1
        else:
            W = [peso(f) for f in fs]; lim = lambda x: re.sub(r"^[^\w¿¡]+|[^\w]+$", "", x.lower())
            idx = next((k for k, f in enumerate(fs) if lim(f["d"]) == lim(c["at"])), None)
            if idx is None: idx = next((k for k, f in enumerate(fs) if c["at"].lower() in f["d"].lower()), None)
            if idx is None: raise SystemExit(f"escena {i+1}: el pie '{name}' busca «{c['at']}» y no esta en la frase {c['s']+1}")
            t = t0 + (t1 - t0) * sum(W[:idx]) / sum(W)
        cue[name] = round(t + c.get("off", 0), 3)
    sc.update({"a0": round(a0, 3), "a1": round(a1, 3), "sent": sent, "caps": caps, "cue": cue})
    pistas.append((a0, s)); T = a1 + gap + sc.get("hold", 0)
    if not EXTERNO:
        os.makedirs(WORK + "/lineas", exist_ok=True); sf.write(f"{WORK}/lineas/l{i+1:02d}.wav", s, SR)
    pal = len(texto.split())
    print(f"escena {i+1} {sc['type']:10s} {len(s)/SR:5.2f}s | {pal/(len(s)/SR)*60:3.0f} pal/min | intento {intento} | guion {r:.3f} | frases {' '.join(f'{x:.2f}' for x in ok_fr)}" + (f" | {'; '.join(dif[:3])}" if dif else ""), flush=True)

total = T - gap - spec["scenes"][-1].get("hold", 0) + tail
fps = spec["fps"]; nfr = int(round(total * fps)); total = nfr / fps
# limites visuales: la escena cambia en el medio del silencio entre dos narraciones
sc = spec["scenes"]
for i, s_ in enumerate(sc):
    s_["T0"] = 0.0 if i == 0 else round(max(sc[i - 1]["a1"] + 0.2, s_["a0"] - 0.33), 3)   # la escena cambia justo antes de que vuelva la voz
for i, s_ in enumerate(sc): s_["T1"] = total if i == len(sc) - 1 else sc[i + 1]["T0"]
spec["frames"] = [int(round(s_["T0"] * fps)) for s_ in sc]; spec["frames_total"] = nfr; spec["total"] = total

mix = np.zeros(int(total * SR) + SR, dtype=np.float32)
for a0, s in pistas: mix[int(a0 * SR): int(a0 * SR) + len(s)] += s
mix = mix[: int(total * SR)]
sf.write(WORK + "/voz_cruda.wav", mix, SR)
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", WORK + "/voz_cruda.wav", "-af", NIVEL, "-ar", "48000", "-ac", "2", WORK + "/voz.wav"], check=True)
err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", WORK + "/voz.wav", "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
summ = err[err.rfind("Summary:"):]
lufs = re.search(r"I:\s+(-?[\d.]+) LUFS", summ).group(1); pico = re.search(r"Peak:\s+(-?[\d.]+) dBFS", summ).group(1)
spec["voz"] = {"motor": "externo" if EXTERNO else "supertonic-3", "voz": os.path.basename(EXTERNO.rstrip("/")) if EXTERNO else VOZ, "velocidad": VEL, "lufs": float(lufs)}
json.dump(spec, open(WORK + "/spec.timed.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
pal = sum(len(" ".join(dicho(fichas(x)) for x in s_["narr"]).split()) for s_ in sc)
print(f"TOTAL {total:.2f}s | {nfr} cuadros | {pal} palabras | {lufs} LUFS | pico {pico} dBFS | {len(avisos)} aviso(s)")
for a in avisos: print("AVISO:", a)
