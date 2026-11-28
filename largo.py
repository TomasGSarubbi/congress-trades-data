"""Arma y filma un video largo (horizontal, 1920x1080) de Cifra Clave a partir de spec.timed.json.

Uso:
  python3 largo.py build  <engine.html> <carpeta>            -> valida y escribe <carpeta>/largo.html
  python3 largo.py merge  <spec.json> <carpeta>              -> refresca lo visual en spec.timed.json sin rehacer la voz
  python3 largo.py stills <carpeta> [t1 t2 ...]              -> <carpeta>/stills/tNNN.NN.jpg + sheet.jpg (sin tiempos: 2 por escena)
  python3 largo.py video  <carpeta> [s3 s5 ...]              -> <carpeta>/scenes/sN.mp4 (todas o las nombradas)
  python3 largo.py finish <carpeta> <salida.mp4>             -> une escenas, agrega <carpeta>/voz.wav y revisa el archivo
  python3 largo.py sheet  <video.mp4> <hoja.jpg> [cada_s]    -> hoja de contactos del video final
"""
import sys, os, re, json, subprocess, time

W, H = 1920, 1080
TYPES = {"contrato": ["year", "price", "sub", "docTitle"], "origen": ["yearFrom", "yearTo", "price", "count"], "compra": ["total", "from", "to"],
         "propuesta": ["a", "b", "stamp"], "red": ["cols", "rows", "from", "toText"], "venta": ["a", "b"], "hoy": ["big", "bigUnit", "chain"], "cierre": ["tag", "legal"], "cartas": ["cards"], "dato": ["ic"], "cita": ["text", "ic"], "linea": ["pts"]}

def check(spec):
    E, Wn = [], []
    for i, s in enumerate(spec.get("scenes") or [], 1):
        ty = s.get("type")
        if ty not in TYPES: E.append(f"escena {i}: tipo desconocido '{ty}'"); continue
        for f in TYPES[ty]:
            if f not in s: E.append(f"escena {i} ({ty}): falta '{f}'")
        if "caps" not in s: E.append(f"escena {i}: sin tiempos (correr largo_audio.py primero)"); continue
        for c in s["caps"]:
            plain = re.sub(r"<[^>]+>", "", c["html"])
            if len(plain) > 52: Wn.append(f"escena {i}: subtitulo largo ({len(plain)}): {plain!r}")
            if c["t1"] - c["t0"] < 0.45: Wn.append(f"escena {i}: subtitulo de {c['t1']-c['t0']:.2f}s, muy breve: {plain!r}")
        for k, v in (s.get("cue") or {}).items():
            if not s["T0"] - 0.01 <= v <= s["T1"] + 0.01: Wn.append(f"escena {i}: el pie '{k}' ({v}) cae fuera de la escena")
    if not spec.get("scenes"): E.append("no hay escenas")
    return E, Wn

def chrome(pw):
    args = ["--no-sandbox", "--hide-scrollbars", "--force-device-scale-factor=1"]
    try: b = pw.chromium.launch(channel="chrome", headless=True, args=args)
    except Exception: b = pw.chromium.launch(headless=True, args=args)
    return b, b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)

def open_page(pg, work):
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("file://" + os.path.abspath(work) + "/largo.html"); pg.evaluate("document.fonts.ready.then(()=>1)")
    if errs: raise SystemExit("ERROR en la pagina: " + " | ".join(errs[:3]))
    return errs

cmd = sys.argv[1]
if cmd == "build":
    engine, work = sys.argv[2:4]
    spec = json.load(open(work + "/spec.timed.json", encoding="utf-8"))
    E, Wn = check(spec)
    for w in Wn: print("AVISO:", w)
    for e in E: print("ERROR:", e)
    if E: raise SystemExit(f"{len(E)} error(es)")
    fl = subprocess.run(["fc-list"], capture_output=True, text=True).stdout
    if not (re.search(r"Anton", fl) and re.search(r"Inter[,:]", fl)): raise SystemExit("ERROR: faltan las fuentes Anton y/o Inter")
    open(work + "/largo.html", "w", encoding="utf-8").write(open(engine, encoding="utf-8").read().replace("/*SPEC*/", json.dumps(spec, ensure_ascii=False)))
    json.dump({"fps": spec["fps"], "frames": spec["frames"], "total": spec["frames_total"]}, open(work + "/scenes.json", "w"))
    print("largo.html listo |", len(spec["scenes"]), "escenas |", spec["frames_total"], "cuadros |", round(spec["total"], 1), "s |", len(Wn), "aviso(s)")

elif cmd == "merge":
    src, work = sys.argv[2:4]
    new = json.load(open(src, encoding="utf-8")); old = json.load(open(work + "/spec.timed.json", encoding="utf-8"))
    TIEMPOS = ("a0", "a1", "sent", "caps", "cue", "T0", "T1")
    for i, (a, b) in enumerate(zip(new["scenes"], old["scenes"]), 1):
        if a["narr"] != b["narr"] or a.get("cues") != b.get("cues"): raise SystemExit(f"escena {i}: cambio el guion o los pies -> volver a correr largo_audio.py")
        for k in TIEMPOS: a[k] = b[k]
    for k in ("frames", "frames_total", "total", "voz"): new[k] = old[k]
    json.dump(new, open(work + "/spec.timed.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("spec.timed.json actualizado con lo visual de", src)

elif cmd == "stills":
    from playwright.sync_api import sync_playwright
    work, times = sys.argv[2], [float(x) for x in sys.argv[3:]]
    if not times:
        S = json.load(open(work + "/scenes.json")); fps = S["fps"]; b = S["frames"] + [S["total"]]
        for i in range(len(b) - 1): times += [round((b[i] + (b[i + 1] - b[i]) * 0.5) / fps, 2), round((b[i + 1] - 14) / fps, 2)]
    os.makedirs(work + "/stills", exist_ok=True)
    for f in os.listdir(work + "/stills"): os.remove(work + "/stills/" + f)
    with sync_playwright() as p:
        b, pg = chrome(p); open_page(pg, work)
        for t in times:
            pg.evaluate(f"render({t})"); pg.screenshot(path=f"{work}/stills/t{t:06.2f}.jpg", type="jpeg", quality=88)
        b.close()
    cols = min(len(times), 4); rows = -(-len(times) // cols)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-pattern_type", "glob", "-i", work + "/stills/t*.jpg", "-vf", f"scale=640:-1,tile={cols}x{rows}:padding=8:color=white", "-frames:v", "1", "-q:v", "3", work + "/stills/sheet.jpg"], check=True)
    print("stills:", " ".join(f"{t:.2f}" for t in times), "->", work + "/stills/sheet.jpg")

elif cmd == "video":
    from playwright.sync_api import sync_playwright
    work, only = sys.argv[2], set(sys.argv[3:])
    S = json.load(open(work + "/scenes.json")); fps = S["fps"]; bounds = S["frames"] + [S["total"]]
    os.makedirs(work + "/scenes", exist_ok=True)
    enc = ["-vf", "scale=in_color_matrix=bt601:in_range=pc:out_color_matrix=bt709:out_range=tv,format=yuv420p", "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
           "-pix_fmt", "yuv420p", "-g", "60", "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-r", str(fps), "-video_track_timescale", "15360"]
    t0 = time.time(); bad = 0; n = 0
    with sync_playwright() as p:
        b, pg = chrome(p); open_page(pg, work)
        for i in range(len(bounds) - 1):
            name = f"s{i+1}"
            if only and name not in only: continue
            tmp, dst = f"{work}/scenes/{name}.tmp.mp4", f"{work}/scenes/{name}.mp4"
            ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-"] + enc + [tmp], stdin=subprocess.PIPE)
            for f in range(bounds[i], bounds[i + 1]):
                pg.evaluate(f"render({f / fps})"); ff.stdin.write(pg.screenshot(type="jpeg", quality=92)); n += 1
            ff.stdin.close(); rc = ff.wait()
            if rc == 0: os.replace(tmp, dst)
            else: bad += 1
            print(f"{name}: cuadros {bounds[i]}-{bounds[i+1]} rc={rc} t={time.time()-t0:.0f}s ({n/(time.time()-t0):.1f} cuadros/s)", flush=True)
        b.close()
    if bad: raise SystemExit(f"{bad} escena(s) fallaron")

elif cmd == "finish":
    work, out = sys.argv[2:4]
    S = json.load(open(work + "/scenes.json")); n = len(S["frames"])
    with open(work + "/scenes/list.txt", "w") as f:
        for i in range(n): f.write(f"file '{os.path.abspath(work)}/scenes/s{i+1}.mp4'\n")
    tmpv, tmpo = work + "/scenes/video.tmp.mp4", out[:-4] + ".tmp.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", work + "/scenes/list.txt", "-c", "copy", tmpv], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmpv, "-i", work + "/voz.wav", "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", tmpo], check=True)
    os.replace(tmpo, out)
    pr = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,size:stream=codec_type,codec_name,width,height,nb_frames", "-of", "json", out], capture_output=True, text=True).stdout)
    v = [s for s in pr["streams"] if s["codec_type"] == "video"]; a = [s for s in pr["streams"] if s["codec_type"] == "audio"]
    dur, size = float(pr["format"]["duration"]), int(pr["format"]["size"])
    ok = bool(v) and bool(a) and v[0]["width"] == W and v[0]["height"] == H and int(v[0]["nb_frames"]) == S["total"] and abs(dur - S["total"] / S["fps"]) < 0.2
    print(f"{out}: {v[0]['width']}x{v[0]['height']} {v[0]['codec_name']} {v[0]['nb_frames']} cuadros | audio {a[0]['codec_name'] if a else 'FALTA'} | {dur:.2f}s | {size/1e6:.1f} MB | {'OK' if ok else 'REVISAR'}")
    if not ok: raise SystemExit("El archivo final no coincide con lo esperado (cuadros, tamano o audio).")

elif cmd == "sheet":
    src, dst = sys.argv[2:4]; cada = float(sys.argv[4]) if len(sys.argv) > 4 else 5
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src], capture_output=True, text=True).stdout)
    n = max(1, int(dur // cada)); cols = min(n, 5); rows = -(-n // cols)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vf", f"fps=1/{cada}:start_time={cada/2},scale=480:-1,tile={cols}x{rows}:padding=6:color=white", "-frames:v", "1", "-q:v", "3", dst], check=True)
    print("hoja:", dst, "|", n, "cuadros")
