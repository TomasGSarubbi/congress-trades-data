"""Genera la narracion y los tiempos de un Short a partir de spec.json.

Uso: python3 -I make_audio.py <modelo.onnx> <voices.bin> <spec.json> <carpeta_salida>

Escribe en <carpeta_salida>:
  voz_raw.wav      voz tal como sale del modelo
  voz.wav          voz final: ecualizada (mas calida), comprimida suave y normalizada a -14 LUFS
  spec.timed.json  el mismo spec con start/end por linea, por fragmento de subtitulo y por escena (30 fps)
"""
import sys, json, re, subprocess
import numpy as np, soundfile as sf
from kokoro_onnx import Kokoro

model, voices, spec_path, outdir = sys.argv[1:5]
spec = json.load(open(spec_path, encoding="utf-8"))
V = spec.get("voice", {})
voice, speed, lang = V.get("name", "em_alex"), float(V.get("speed", 1.0)), V.get("lang", "es-419")
FPS, LEAD, TAIL = 30, 0.20, 0.90
# Cadena "voz calida": quita graves inutiles, sube cuerpo, baja brillo, compresion suave, volumen parejo.
CHAIN = ("highpass=f=70,bass=g=2.5:f=150:w=0.8,treble=g=-2.5:f=6000:w=0.7,"
         "acompressor=threshold=-21dB:ratio=2.2:attack=10:release=150:makeup=1.5,loudnorm=I=-14:TP=-1.5:LRA=11")

def weight(s):
    s = re.sub(r"[*¿¡]", "", s).strip()
    return len(s) + (4 if s.endswith(",") else 0) + (6 if s.endswith((".", ":", "?", "!")) else 0)

def loudness(path):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    summ = err[err.rfind("Summary:"):]
    return float(re.search(r"I:\s+(-?[\d.]+) LUFS", summ).group(1)), float(re.search(r"Peak:\s+(-?[\d.]+) dBFS", summ).group(1))

k = Kokoro(model, voices)
sr = 24000
parts = [np.zeros(int(LEAD * sr), dtype=np.float32)]
t = LEAD
for si, sc in enumerate(spec["scenes"]):
    for li, line in enumerate(sc["lines"]):
        last = li == len(sc["lines"]) - 1
        gap = float(line.get("gap", 0.30 if last else 0.45))
        s, sr = k.create(line["tts"], voice=voice, speed=speed, lang=lang)
        s = np.asarray(s, dtype=np.float32)
        thr = 0.02 * float(np.abs(s).max()); idx = np.where(np.abs(s) > thr)[0]
        s = s[max(0, idx[0] - int(0.03 * sr)): min(len(s), idx[-1] + int(0.06 * sr))]
        d = len(s) / sr
        caps = [c if isinstance(c, list) else [c, c] for c in line["caps"]]   # [texto en pantalla, texto hablado]
        ws = [weight(sp) for _, sp in caps]; tot = sum(ws); c0 = t; timed = []
        for (disp, _), w in zip(caps, ws):
            c1 = c0 + d * w / tot
            timed.append({"text": disp, "start": round(c0, 3), "end": round(c1, 3)}); c0 = c1
        line.update({"start": round(t, 3), "end": round(t + d, 3), "caps": timed})
        parts += [s, np.zeros(int(gap * sr), dtype=np.float32)]
        print(f"escena {si+1} linea {li+1}: {d:5.2f}s inicio {t:6.2f} | {line['tts'][:58]}")
        t += d + gap
parts.append(np.zeros(int(max(0.0, TAIL - 0.30) * sr), dtype=np.float32))
audio = np.concatenate(parts)
total = len(audio) / sr
starts = [0] + [round((sc["lines"][0]["start"] - 0.10) * FPS) for sc in spec["scenes"][1:]]
frames_total = int(-(-total * FPS // 1))
for i, sc in enumerate(spec["scenes"]):
    sc["start"] = starts[i] / FPS
    sc["end"] = (starts[i + 1] if i + 1 < len(starts) else frames_total) / FPS
spec.update({"total": round(total, 3), "fps": FPS, "frames": starts, "frames_total": frames_total})
raw, pre, out = f"{outdir}/voz_raw.wav", f"{outdir}/voz_pre.wav", f"{outdir}/voz.wav"
sf.write(raw, audio, sr)
json.dump(spec, open(f"{outdir}/spec.timed.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("TOTAL:", round(total, 2), "s |", frames_total, "cuadros | escenas en cuadros:", starts)

subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-af", CHAIN, "-ar", "48000", "-ac", "2", pre], check=True)
I, P = loudness(pre)
gain = min(-14.0 - I, -1.0 - P)          # llegar a -14 LUFS sin pasar de -1 dB de pico
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", pre, "-af", f"volume={gain:.2f}dB", "-ar", "48000", "-ac", "2", out], check=True)
I2, P2 = loudness(out)
print(f"voz.wav lista: {I2:.1f} LUFS, pico {P2:.1f} dB (objetivo -14 LUFS)")
