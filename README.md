# Cifra Clave — kit de videos largos («Historias de empresas»)

Videos horizontales (1920x1080, 30 fps) de unos 10 minutos, 100% gráficos, con la misma voz de los Shorts
(Supertonic M1) a velocidad normal. Este kit vive en la rama `largos-kit`; el de los Shorts, en `shorts-kit`.
Nunca tocar `main` ni la rama `shorts-kit` desde acá.

## Preparar el entorno
1. Clonar las dos ramas: `shorts-kit` en `kit/` y `largos-kit` en `lk/`.
2. `bash kit/setup.sh` (instala fuentes Anton e Inter, la voz Supertonic y el oído Whisper en `~/.cache/cifra-clave`).
3. `pip install --break-system-packages num2words praat-parselmouth` si faltan.

## Pasos de un video
1. **Elegir empresa**: la primera de `registro.json > proximas` que no esté en `publicados`.
2. **Investigar** en fuentes primarias (sitio de la empresa, presentaciones ante reguladores) y medios serios.
   Ninguna cifra sin fuente consultada hoy o sin cálculo propio (y se rotula «cálculo propio»).
   Si dos fuentes se contradicen, no usar el dato.
3. **Escribir el spec** (`trabajo/spec.json`) copiando la forma de `ejemplos/coca-cola.json`:
   25 a 32 escenas, unas 1.250 a 1.500 palabras (9 a 11 minutos). Español neutro, sin voseo, tono conversacional.
   Un gancho en la primera escena, una pregunta que se responde al final, y un repaso antes del cierre.
4. **Voz y tiempos**: `python3 -I largo_audio.py trabajo/spec.json trabajo/w --voz M1 --vel 1.0 --pasos 16`
   (tarda unos 30 s por escena). Los avisos por nombres propios en inglés son normales; cualquier otro, corregir el guion.
5. **Armar y revisar**: `python3 -I largo.py build engine.html trabajo/w` y después
   `python3 -I largo.py stills trabajo/w <un tiempo cerca del final de cada escena>`. Mirar la hoja: nada encimado ni cortado.
   Para corregir solo lo visual: editar el spec y `python3 -I largo.py merge trabajo/spec.json trabajo/w` + `build`.
6. **Filmar** en dos procesos a la vez (repartir las escenas en dos listas parejas):
   `python3 -I largo.py video trabajo/w s1 s3 ...` y `python3 -I largo.py video trabajo/w s2 s4 ...`
   (unos 17 cuadros por segundo entre los dos: 10 minutos de video son unos 17 minutos).
7. **Cerrar**: `python3 -I largo.py finish trabajo/w salida.mp4` y `python3 -I largo.py sheet salida.mp4 hoja.jpg 20`. Mirar la hoja.
8. **Miniatura**: copiar `miniaturas/coca-cola.html`, cambiar textos y dibujo, y `python3 -I mini.py miniaturas/x.html x.png`.
   Texto de 3 a 5 palabras, una cifra gigante, un dibujo genérico. Mirarla antes de entregar.
9. **Entregar** al usuario: video, miniatura, título (menos de 70 caracteres), descripción con fuentes y capítulos
   (tiempos `T0` de las escenas clave), y la leyenda «Contenido informativo. No es recomendación de inversión. Voz generada con IA.»
10. **Registrar**: mover la empresa a `publicados` en `registro.json`, guardar el spec en `ejemplos/` y la miniatura en `miniaturas/`,
    y hacer commit y push solo a `largos-kit`.

## Reglas del canal
- Sin logos, envases ni personajes de marca: se nombra a la empresa, pero los dibujos son genéricos.
- Sin fotos ni caricaturas de personas reales. La voz no se presenta como experta.
- No es asesoramiento: nada de «conviene comprar». Va siempre la leyenda legal en el cierre.
- Citas traducidas: cortas, atribuidas y marcadas «(traducción)».

## El guion dentro del spec
`narr` es una lista de frases por escena. `{1899|mil ochocientos noventa y nueve}` muestra lo de la izquierda y dice lo de la
derecha (usarlo en años, cifras y nombres extranjeros: `{Woodruff|Wúdraf}`). `*texto*` resalta en el subtítulo.
`cues` ata lo que aparece en pantalla a una palabra: `{"c0": {"s": 1, "at": "precio"}}` = frase 2, palabra «precio».
`hold` agrega segundos al final de la escena. `chip` es la etiqueta de arriba a la derecha (año o tema).
Escenas de hasta ~330 caracteres: si es más larga, partirla en dos.

## Tipos de escena generales (usar sobre todo estos)
- `cartas`: `kicker`, `head` (opcional), `cards: [{ic, big, label}]` (2 a 5). Pies `c0`, `c1`...
- `dato`: `kicker`, `big` (texto) o `num` (cuenta desde 0, con `pre`/`suf`), `unit`, `sub`, `chips` (lista), `ic`, `artW/artX/artY`. Pies `big`, `sub`, `art`, `chip0`...
- `cita`: `kicker`, `text` (HTML con `<b>`), `by`, `ic`. Pies `text`, `art`.
- `linea`: `kicker`, `head` (opcional), `pts: [{y, label, ic}]` (3 o 4). Pies `p0`, `p1`...
- `cierre`: `tag`, `sources`, `legal`, `recap` (dos cifras). Pies `recapA`, `recapB`, `marca`.
- Cualquier escena admite `art`: dibujos sueltos `[{ic, x, y, w, at, d, rot}]`.

Tipos hechos para Coca-Cola que se pueden reutilizar si la historia lo pide (ver el ejemplo): `contrato`, `origen`, `compra`,
`propuesta`, `red`, `venta`, `hoy`.

## Dibujos disponibles (`ic`)
shop, coin, bill, factory, truck, globe, bag, person, crate, pen, ticket, bottle, helmet, phone, vending, medal, hourglass,
vault, glass, flask, spark, squig, plus, ring. Para uno nuevo, agregarlo en `engine.html` dentro de `ART` (SVG 200x200,
trazo crema de 8 px, rellenos planos con los colores de la marca) y probarlo con `stills`.
