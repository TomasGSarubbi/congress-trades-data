"""Arma short.html desde engine.html + spec.timed.json y lo filma con Chrome.

Uso:
  python3 render.py build  <engine.html> <spec.timed.json> <carpeta>   -> valida el spec y escribe <carpeta>/short.html
  python3 render.py stills <carpeta> [t1 t2 ...]                       -> <carpeta>/stills/tNN.NN.jpg + sheet.jpg
                                                                          (sin tiempos: 2 cuadros por escena, mitad y final)
  python3 render.py video  <carpeta> [s3 s5 ...]                       -> <carpeta>/scenes/sN.mp4 (todas o las nombradas)
  python3 render.py finish <carpeta> <voz.wav> <salida.mp4>            -> une escenas, agrega el audio, revisa el archivo
  python3 render.py sheet  <video.mp4> <hoja.jpg>                      -> hoja de contactos del video final (1 cuadro cada 2 s)
"""
import sys, os, re, json, subprocess, time

TYPES = {  # tipo de escena -> campos obligatorios
    "people": ["count", "title", "subtitle"], "asset": ["ticker", "name", "calendar"], "ranges": ["max", "rows"],
    "question": ["question"], "merge": ["a", "b"], "payout": ["value"], "equation": ["left", "right"],
    "bars": ["rows"], "columns": ["cols"], "steps": ["nodes"], "stat": [], "line": ["series"], "split": ["parts"], "outro": [],
}

def check(spec):
    """Devuelve (errores, avisos). Los errores frenan el build; los avisos hay que leerlos y decidir."""
    E, W = [], []
    if not spec.get("brand"): E.append("falta 'brand' (nombre del canal)")
    sc = spec.get("scenes") or []
    if not sc: E.append("no hay escenas")
    for i, s in enumerate(sc, 1):
        ty = s.get("type")
        if ty not in TYPES: E.append(f"escena {i}: tipo desconocido '{ty}' (validos: {', '.join(TYPES)})"); continue
        for f in TYPES[ty]:
            if f not in s: E.append(f"escena {i} ({ty}): falta '{f}'")
        if ty == "stat" and "value" not in s and "text" not in s: E.append(f"escena {i} (stat): falta 'value' o 'text'")
        if ty == "line":
            ns = {len(z.get("values", [])) for z in s.get("series", [])}
            if len(ns) != 1 or min(ns) < 2: E.append(f"escena {i} (line): todas las series necesitan la misma cantidad de valores (2 o mas)")
        if not s.get("lines"): E.append(f"escena {i} ({ty}): falta 'lines' (toda escena lleva al menos una frase)"); continue
        ncap = 0
        for j, l in enumerate(s["lines"], 1):
            tts = l.get("tts", "")
            if not tts.strip(): E.append(f"escena {i} linea {j}: 'tts' vacio")
            if re.search(r"\d", tts): W.append(f"escena {i} linea {j}: hay cifras en 'tts' -> escribirlas en letras para la voz: {tts!r}")
            if re.search(r"USD|%|\$|&", tts): W.append(f"escena {i} linea {j}: simbolos en 'tts' (USD, %, $) -> escribir la palabra: {tts!r}")
            if not l.get("caps"): E.append(f"escena {i} linea {j}: falta 'caps'"); continue
            for c in l["caps"]:
                txt = c.get("text") if isinstance(c, dict) else (c[0] if isinstance(c, list) else c)
                plain = txt.replace("*", "")
                ncap += 1
                if len(plain) > 40: W.append(f"escena {i}: subtitulo largo ({len(plain)} letras, max 40): {plain!r}")
                if any(len(w) > 17 for w in plain.split()): W.append(f"escena {i}: palabra muy larga en subtitulo: {plain!r}")
        for key in [k for k in s if k.endswith("Cue")]:
            if isinstance(s[key], int) and s[key] >= ncap: W.append(f"escena {i}: {key}={s[key]} pero la escena tiene {ncap} fragmentos de subtitulo (0..{ncap-1})")
        if "start" in s and s["end"] - s["start"] < 1.5: W.append(f"escena {i}: dura {s['end']-s['start']:.1f}s, muy corta para leerla")
    if sc and sc[-1].get("type") != "outro": W.append("la ultima escena no es 'outro' (falta cierre con marca y aviso legal)")
    tot = spec.get("total")
    if tot is not None and not 18 <= tot <= 58: W.append(f"duracion {tot:.1f}s fuera del rango recomendado 25-45s (maximo 58)")
    return E, W

def fonts_ok():
    try: out = subprocess.run(["fc-list"], capture_output=True, text=True).stdout
    except FileNotFoundError: return True
    return all(re.search(n, out) for n in (r"Anton", r"Inter[,:]"))

def chrome(pw):
    args = ["--no-sandbox", "--hide-scrollbars", "--force-device-scale-factor=1"]
    try: b = pw.chromium.launch(channel="chrome", headless=True, args=args)
    except Exception: b = pw.chromium.launch(headless=True, args=args)
    return b, b.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)

def open_page(pg, work):
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("file://" + os.path.abspath(work) + "/short.html"); pg.evaluate("document.fonts.ready.then(()=>1)")
    if errs: raise SystemExit("ERROR en la pagina: " + " | ".join(errs[:3]))
    return errs

cmd = sys.argv[1]
if cmd == "build":
    engine, spec_path, work = sys.argv[2:5]
    spec = json.load(open(spec_path, encoding="utf-8"))
    E, W = check(spec)
    for w in W: print("AVISO:", w)
    for e in E: print("ERROR:", e)
    if E: raise SystemExit(f"{len(E)} error(es) en el spec: corregir y volver a correr make_audio.py + build")
    if not fonts_ok(): raise SystemExit("ERROR: faltan las fuentes Anton y/o Inter. Correr setup.sh (las instala desde fonts/).")
    html = open(engine, encoding="utf-8").read().replace("/*SPEC*/", json.dumps(spec, ensure_ascii=False))
    os.makedirs(work, exist_ok=True)
    open(work + "/short.html", "w", encoding="utf-8").write(html)
    json.dump({"fps": spec["fps"], "frames": spec["frames"], "total": spec["frames_total"]}, open(work + "/scenes.json", "w"))
    print("short.html listo |", len(spec["scenes"]), "escenas |", spec["frames_total"], "cuadros |", round(spec["total"], 1), "s |", len(W), "aviso(s)")

elif cmd == "stills":
    from playwright.sync_api import sync_playwright
    work, times = sys.argv[2], [float(x) for x in sys.argv[3:]]
    if not times:
        S = json.load(open(work + "/scenes.json")); fps = S["fps"]; b = S["frames"] + [S["total"]]
        for i in range(len(b) - 1): times += [round((b[i] + (b[i + 1] - b[i]) * 0.45) / fps, 2), round((b[i + 1] - 4) / fps, 2)]
    os.makedirs(work + "/stills", exist_ok=True)
    for f in os.listdir(work + "/stills"): os.remove(work + "/stills/" + f)
    with sync_playwright() as p:
        b, pg = chrome(p); open_page(pg, work)
        for t in times:
            pg.evaluate(f"render({t})"); pg.screenshot(path=f"{work}/stills/t{t:05.2f}.jpg", type="jpeg", quality=90)
        b.close()
    cols = min(len(times), 8); rows = -(-len(times) // cols)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-pattern_type", "glob", "-i", work + "/stills/t*.jpg", "-vf", f"scale=380:-1,tile={cols}x{rows}:padding=6:color=white", "-frames:v", "1", work + "/stills/sheet.jpg"], check=True)
    print("stills:", " ".join(f"{t:.2f}" for t in times), "->", work + "/stills/sheet.jpg")

elif cmd == "video":
    from playwright.sync_api import sync_playwright
    work, only = sys.argv[2], set(sys.argv[3:])
    S = json.load(open(work + "/scenes.json")); fps = S["fps"]; bounds = S["frames"] + [S["total"]]
    os.makedirs(work + "/scenes", exist_ok=True)
    enc = ["-vf", "scale=in_color_matrix=bt601:in_range=pc:out_color_matrix=bt709:out_range=tv,format=yuv420p", "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
           "-pix_fmt", "yuv420p", "-g", "60", "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-r", str(fps), "-video_track_timescale", "15360"]
    t0 = time.time(); bad = 0
    with sync_playwright() as p:
        b, pg = chrome(p); open_page(pg, work)
        for i in range(len(bounds) - 1):
            name = f"s{i+1}"
            if only and name not in only: continue
            tmp, dst = f"{work}/scenes/{name}.tmp.mp4", f"{work}/scenes/{name}.mp4"
            ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-"] + enc + [tmp], stdin=subprocess.PIPE)
            for f in range(bounds[i], bounds[i + 1]):
                pg.evaluate(f"render({f / fps})"); ff.stdin.write(pg.screenshot(type="jpeg", quality=92))
            ff.stdin.close(); rc = ff.wait()
            if rc == 0: os.replace(tmp, dst)
            else: bad += 1
            print(f"{name}: cuadros {bounds[i]}-{bounds[i+1]} rc={rc} t={time.time()-t0:.0f}s", flush=True)
        b.close()
    if bad: raise SystemExit(f"{bad} escena(s) fallaron")

elif cmd == "finish":
    work, voz, out = sys.argv[2:5]
    S = json.load(open(work + "/scenes.json")); n = len(S["frames"])
    with open(work + "/scenes/list.txt", "w") as f:
        for i in range(n): f.write(f"file '{os.path.abspath(work)}/scenes/s{i+1}.mp4'\n")
    tmpv, tmpo = work + "/scenes/video.tmp.mp4", out[:-4] + ".tmp.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", work + "/scenes/list.txt", "-c", "copy", tmpv], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmpv, "-i", voz, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", tmpo], check=True)
    os.replace(tmpo, out)
    pr = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,size:stream=codec_type,codec_name,width,height,nb_frames", "-of", "json", out], capture_output=True, text=True).stdout)
    v = [s for s in pr["streams"] if s["codec_type"] == "video"]; a = [s for s in pr["streams"] if s["codec_type"] == "audio"]
    dur, size = float(pr["format"]["duration"]), int(pr["format"]["size"])
    ok = bool(v) and bool(a) and v[0]["width"] == 1080 and v[0]["height"] == 1920 and int(v[0]["nb_frames"]) == S["total"] and abs(dur - S["total"] / S["fps"]) < 0.2
    print(f"{out}: {v[0]['width']}x{v[0]['height']} {v[0]['codec_name']} {v[0]['nb_frames']} cuadros | audio {a[0]['codec_name'] if a else 'FALTA'} | {dur:.2f}s | {size/1e6:.1f} MB | {'OK' if ok else 'REVISAR'}")
    if not ok: raise SystemExit("El archivo final no coincide con lo esperado (cuadros, tamano o audio).")

elif cmd == "sheet":
    src, dst = sys.argv[2:4]
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src], capture_output=True, text=True).stdout)
    n = max(1, int(dur // 2)); cols = min(n, 8); rows = -(-n // cols)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vf", f"fps=1/2:start_time=1,scale=300:-1,tile={cols}x{rows}:padding=6:color=white", "-frames:v", "1", dst], check=True)
    print("hoja:", dst, "|", n, "cuadros")
