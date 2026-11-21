# Cifra Clave · kit de Shorts

Todo lo necesario para producir un Short vertical (1080×1920, 30 fps, 25–45 s) del canal
**Cifra Clave — «El dinero, explicado con datos.»**: voz, gráficos animados y subtítulos,
sin servicios pagos. Se escribe un archivo `spec.json` (el guion + qué gráfico va en cada
escena) y el kit hace el resto.

Esta rama (`shorts-kit`) es independiente del resto del repo: no toca `main` ni el tracker.

| Archivo | Para qué |
|---|---|
| `setup.sh` | Prepara una sesión nueva (voz, fuentes, Chrome). Correrlo siempre primero. |
| `make_audio.py` | Voz (Kokoro, `em_alex`) + ecualización cálida + tiempos de cada subtítulo. |
| `engine.html` | Motor de escenas animadas. No se edita para un video normal. |
| `render.py` | Valida el spec, saca cuadros de revisión, filma y arma el `.mp4`. |
| `publicados/` | El spec de cada video ya hecho. Sirven de ejemplo y permiten rehacer un video (por ejemplo, si cambia el nombre del canal). |
| `registro.json` | Qué videos ya se hicieron (para no repetir temas). |
| `aprendizajes.md` | Qué funcionó y qué no según las métricas del canal. Leer antes de elegir tema. |
| `fonts/` | Anton e Inter (licencia OFL), por si la sesión no las trae instaladas. |

---

## 1. Producir un video, paso a paso

```bash
git clone --depth 1 --single-branch -b shorts-kit https://github.com/TomasGSarubbi/congress-trades-data kit
bash kit/setup.sh                       # termina con "LISTO"; si dice "HAY FALTANTES", frenar y avisar
M=$HOME/.cache/cifra-clave/kokoro; W=trabajo; mkdir -p $W
# escribir $W/spec.json (secciones 2 a 4)
python3 -I kit/make_audio.py $M/kokoro-v1.0.onnx $M/voices-v1.0.bin $W/spec.json $W
python3 kit/render.py build  kit/engine.html $W/spec.timed.json $W    # valida: 0 errores, leer los avisos
python3 kit/render.py stills $W                                       # mirar stills/sheet.jpg (sección 5)
python3 kit/render.py video  $W                                       # 2–3 minutos
python3 kit/render.py finish $W $W/voz.wav cifra-clave_AAAA-MM-DD_tema.mp4    # tiene que terminar en "OK"
python3 kit/render.py sheet  cifra-clave_AAAA-MM-DD_tema.mp4 $W/final.jpg     # mirar el archivo final
```

- Si cambia una frase (`tts` o `caps`): volver a correr desde `make_audio.py`.
- Si cambia solo un gráfico: volver a correr desde `build`. Para refilmar una sola escena: `render.py video $W s4` y después `finish`.
- Un solo render completo por video: los errores se cazan antes, en los cuadros de revisión.

---

## 2. Guía editorial

**Canal.** Finanzas en español para gente curiosa, no para expertos. Cada video gira alrededor
de **una cifra** que se entiende en 30 segundos y se ve en pantalla. Español neutro de
Latinoamérica: sin voseo, sin «vosotros», sin modismos de un solo país.

**Series.** Una por día de la semana (hora de Buenos Aires). El nombre va en `series`
y aparece junto a la marca.

| Día | `series` | De qué trata | Fuente típica |
|---|---|---|---|
| Lunes | `MERCADOS` | La cifra que dejó la semana en los mercados y por qué. | Cierres oficiales, 2 fuentes |
| Martes | `EMPRESA EN CIFRAS` | Una empresa conocida explicada con un número de su último reporte. | Reporte anual o trimestral de la empresa |
| Miércoles | `CONCEPTO` | Un concepto financiero con un ejemplo numérico propio. | Cálculo propio, supuestos a la vista |
| Jueves | `RADAR DEL CONGRESO` | Operaciones declaradas por congresistas de EE.UU. | `data/` de la rama `main` + PDF oficial |
| Viernes | `MACRO` | Un dato publicado en la semana (inflación, tasas, empleo, PIB). | Oficina de estadística o banco central |
| Sábado | `HISTORIA` | Un episodio de la historia del dinero contado en cifras. | Fuentes históricas reconocidas |
| Domingo | `COMPARACIÓN` | Dos cosas frente a frente con datos de largo plazo. | Series oficiales o cálculo propio |

Si la serie del día no tiene una buena historia (por ejemplo, no hubo operaciones interesantes
en el Congreso), hacer un `CONCEPTO` o una `HISTORIA` y decirlo en la entrega.

**Cómo elegir el tema.** Sirve si cumple las cuatro:
1. Hay una cifra concreta, verificable y que sorprende.
2. Se explica en 30 segundos sin simplificar hasta mentir.
3. Se puede dibujar con las escenas de la sección 4.
4. No está en `registro.json` en los últimos 60 días.

Temas de reserva para `CONCEPTO` (usar el primero que no esté en el registro; si no se pudo
leer el registro, usar el número de semana del año para elegir): regla del 72 · inflación y
poder de compra · tasa nominal vs. tasa real · costo de las comisiones a largo plazo ·
diversificación · qué es un ETF · qué es un bono y por qué baja cuando suben las tasas ·
dividendos · precio/ganancia · capitalización de mercado · interés simple vs. compuesto ·
fondo de emergencia · costo de pagar el mínimo de la tarjeta · qué es un punto básico ·
liquidez · riesgo y volatilidad · promediar el costo en el tiempo · qué es un índice ·
tipo de cambio real · costo de oportunidad.

Para `HISTORIA`: tulipanes de 1637 · crac de 1929 · hiperinflación alemana de 1923 ·
Bretton Woods · lunes negro de 1987 · burbuja puntocom · crisis de 2008 · hiperinflación de
Zimbabue · crisis asiática de 1997 · el corralito de 2001 · la burbuja japonesa · el petróleo
en negativo de abril de 2020.

Para `COMPARACIÓN`: oro vs. acciones · acciones vs. bonos · efectivo vs. inflación ·
aportar temprano vs. aportar más · índice vs. fondo activo (después de comisiones) ·
tasa fija vs. variable · dólar vs. inflación de EE.UU.

**Reglas que no se negocian.** Existen porque un canal de finanzas vive de que le crean, y
porque YouTube no monetiza contenido financiero engañoso ni de plantilla.
- **Toda cifra tiene fuente abierta en esta sesión** (documento oficial, reporte de la empresa,
  banco central, el dataset del tracker + su PDF oficial) **o sale de un cálculo hecho con
  código** con los supuestos escritos. Precios y variaciones de mercado: dos fuentes que
  coincidan. Si no se puede verificar, no se usa; si era la cifra central, se cambia de tema.
- **Nunca inventar** datos, citas, fechas ni nombres. Ante la duda, quitarlo.
- **No es asesoramiento.** Nada de «conviene», «hay que comprar», «va a subir». Los ejemplos
  hipotéticos dicen sus supuestos en el `footnote` del cierre junto a «No es recomendación de inversión».
- **Sin predicciones de precios** y sin promesas de rendimiento.
- **Neutral en política.** Hechos de registros públicos, sin adjetivos, mismo trato para todos
  los partidos. No insinuar delitos ni información privilegiada: una coincidencia no es prueba.
- **Personas:** solo figuras públicas en su rol público y con datos de registros oficiales.
  Sin fotos ni caricaturas: íconos genéricos.
- **La voz no es un experto.** No dice «soy», «en mi experiencia», ni se presenta como analista.
- **Cada video es distinto:** otro tema, otro guion, otra combinación de escenas. Nada de
  repetir la misma plantilla cambiando un número.

**Radar del Congreso (jueves).** Los datos están en
`https://raw.githubusercontent.com/TomasGSarubbi/congress-trades-data/main/data/` (`latest.json`,
`transactions.json`, `meta.json`). Tener presente:
- Los montos son **rangos**, no cifras exactas. Decir siempre «entre X e Y».
- Decir de quién es la cuenta: propia, cónyuge, conjunta o hijo dependiente.
- Hay hasta 45 días entre la operación y la declaración: es transparencia con retraso.
- Abrir el PDF oficial (campo `source`) de cada operación que se nombre y leer sus notas.
- Buscar el contexto antes de escribir: fusiones, ofertas de compra, vencimientos, cambios
  de índice. Una «venta» puede ser un pago forzoso por una fusión (pasó con WBD el 7/10/2026).

---

## 3. El guion

- **70 a 95 palabras** en total, 6 a 8 escenas, la última siempre `outro`.
- **Primera frase = gancho**: la cifra o la tensión en los primeros dos segundos.
- Frases cortas. Una idea por escena. Cada frase cambia algo en pantalla.
- Cierre fijo: `"El dinero, explicado con datos. Síguenos en Cifra Clave."`

Cada escena lleva `lines`: una o dos frases. Cada frase tiene:

```json
{"tts": "Invertidos al siete por ciento anual: casi ciento diecisiete mil.",
 "caps": [["Invertidos al *7% anual:*", "Invertidos al siete por ciento anual:"],
          ["casi *117.000.*", "casi ciento diecisiete mil."]],
 "gap": 0.35}
```

- `tts` es lo que **dice la voz**: números en letras, sin símbolos (`USD`, `%`, `$`). Nombres
  extranjeros que la voz pronuncia mal se escriben como suenan (`"Wárner Bros Discóveri"`).
- `caps` son los **subtítulos**, en orden. Cada uno es un texto, o un par
  `["lo que se ve", "lo que se dice en ese tramo"]` cuando difieren (cifras, nombres).
  Lo dicho en todos los tramos, sumado, tiene que ser la frase `tts` completa.
- Máximo 40 letras por subtítulo (mejor menos de 28). `*así*` resalta en amarillo: una o dos palabras por frase.
- `gap` es la pausa después de la frase, en segundos (0.3 normal, 0.5 para dejar respirar).

**Los `cue`.** Los subtítulos de una escena se numeran 0, 1, 2… a través de todas sus frases.
Un campo `…Cue` dice en qué subtítulo aparece un elemento: así el gráfico cambia justo cuando
la voz lo nombra. Ejemplo: `"cues": [0, 2]` en `bars` muestra la primera barra con el subtítulo 0
y la segunda con el 2.

---

## 4. El `spec.json` y las escenas

```json
{"brand": "CIFRA CLAVE", "series": "CONCEPTO",
 "voice": {"name": "em_alex", "speed": 1.0, "lang": "es-419"},
 "scenes": [ {"type": "...", "lines": [...]}, ... ]}
```

Colores disponibles en cualquier campo `color`: `amber` (destacado), `mint` (positivo),
`coral` (negativo o alerta), `soft` (neutro), `white`; en chips también `outline`.
El motor ya respeta las zonas seguras de Shorts: no hay que calcular posiciones.
`foot` (opcional en cualquier escena) pone una línea chica de fuente debajo del gráfico;
no usarlo en `line`, `split`, `columns` ni en `stat` con `dots`, que ocupan ese lugar.

| `type` | Qué muestra | Campos (los `…Cue` son opcionales) |
|---|---|---|
| `stat` | **Una cifra gigante** con contexto. El gancho natural del canal. | `kicker`, `prefix`, `value` (cuenta desde 0) o `text` (fijo), `decimals`, `suffix`, `color`, `label`, `valueCue`; más **uno** de: `chips:[{text,color,cue}]` + `rows:[{label,sub,value,display,color,cue}]` con `max`, o `chips` + `dots:{count,cols,color,cue,dur,label}` (grilla de puntos que se enciende) |
| `line` | **Evolución en el tiempo**, 1 a 3 series que se dibujan. | `title`, `hero:{text,sub,color,cue}`, `series:[{name,color,values:[…],end}]`, `yTicks:[{v,label}]`, `xTicks:[{i,label}]` (`i` = posición en `values`), `yMin`, `yMax`, `marks:[{i,s,label,color,cue,pos}]`, `drawCue`, `drawDur` (segundos que tarda en dibujarse) |
| `columns` | **Comparación** con 2 a 5 columnas verticales. | `title`, `cols:[{label,sub,value,display,color,hl}]`, `max`, `cues:[…]` |
| `bars` | **Ranking** con 2 a 6 barras horizontales (con 2 o 3 se agrandan). | `title`, `rows:[{label,sub,value,display,color}]`, `max`, `cues:[…]` |
| `split` | **Partes de un total** (dona) con porcentajes calculados solos. | `title`, `center:{big,small}`, `parts:[{label,value,display,color,cue}]` (2 a 4) |
| `ranges` | Rangos de monto por fila (ideal para el Congreso). | `title`, `max`, `ticks:[{v,label}]`, `rows:[{name,sub,lo,hi,label}]`, `highlight:{index,cue,valCue,badge}` |
| `people` | N personas como íconos, con número grande. | `count` (hasta 12), `big`, `title`, `subtitle`, `tag`, `tagColor`, `tagCue`, `stamp`, `stampCue`, `mark:{count,color,cue}` (pinta k de n: «7 de cada 10») |
| `asset` | Ficha de una acción + calendario con días marcados. | `ticker`, `name`, `tags:[{text,color,cue}]`, `calendar:{year,month,marks:[{day,color,cue,label}]}` |
| `steps` | Línea de tiempo o proceso de 3 o 4 pasos. | `title`, `nodes:[{chip,text,color}]`, `cues:[…]` |
| `merge` | Dos bloques que se fusionan (compras, fusiones). | `chip`, `kicker`, `a`, `verb`, `b`, `result`, `aCue`, `bCue` |
| `payout` | Cifra + personas que cobran + nota citada. | `prefix`, `value`, `suffix`, `label`, `recipients`, `peopleLabel`, `note:{title,quote}`, `valueCue`, `recipientsCue`, `noteCue` |
| `equation` | A (signo) B: la conclusión en tres palabras. | `kicker`, `left`, `op` (`≠ = > < + × →`), `right`, `leftIcon`, `rightIcon` (`doc`, `person`, `bill`), `leftCue`, `opCue`, `rightCue`, `kickerCue` |
| `question` | Pregunta gigante, con sello de respuesta opcional. | `question` (usar `\n`, hasta 3 renglones cortos), `answer`, `answerCue` |
| `outro` | Cierre con marca, lema y aviso. Siempre última. | `brandLines: ["CIFRA","CLAVE"]`, `tagline`, `footnote` (fuente + fecha de los datos + «No es recomendación de inversión.») |

Consejos que salen de los videos ya hechos:
- Variar: no usar el mismo `type` dos veces seguidas, y no más de dos veces por video.
- Los textos grandes se achican solos para entrar, pero cortos quedan mejor: títulos de hasta
  22 letras, etiquetas de hasta 16.
- En `line`, entre 12 y 40 valores por serie; `drawDur` parecido a lo que dura la frase.
- Las cifras en pantalla van con formato español: `1.234,5`. Aclarar la moneda (`USD`).
- Redondear en la voz («casi ciento diecisiete mil») y dejar el número exacto en pantalla.

Los archivos de `publicados/` muestran casi todas las escenas en uso real: copiar uno parecido como punto de partida.

---

## 5. Control de calidad (antes del render completo)

`render.py stills` sin tiempos saca dos cuadros por escena (mitad y final). Abrir
`stills/sheet.jpg` **y al menos tres cuadros a tamaño completo** (`stills/tNN.NN.jpg`). Revisar:

1. Nada se pisa, nada se corta, nada toca los bordes.
2. Cada número en pantalla es el de la fuente (comparar uno por uno) y coincide con lo que dice la voz.
3. Ortografía: tildes, `¿` y `¡`, nombres propios.
4. El gráfico de cada escena cambia cuando la voz lo nombra (revisar los `cue`).
5. La marca y la serie se ven arriba a la izquierda; el cierre tiene fuente y aviso.
6. Duración entre 25 y 45 segundos.

Corregir y repetir hasta que esté limpio. Después del render, mirar la hoja del archivo final
(`render.py sheet`). No se puede escuchar el audio desde la sesión: `make_audio.py` informa
el volumen (objetivo −14 LUFS) y eso es lo verificable.

---

## 6. Entrega

Archivo: `cifra-clave_AAAA-MM-DD_tema.mp4`. Junto al video, un mensaje corto con:

- **Título** (hasta 60 letras, con la cifra): listo para pegar en YouTube.
- **Descripción** (2 o 3 renglones) + fuentes + «Contenido informativo. No es recomendación de inversión.»
- **Hashtags**: 3 a 5, con `#Shorts` y `#finanzas`.
- **Fuentes**: enlaces usados.
- **Verificado**: qué se comprobó contra la fuente y qué no se pudo comprobar.

Después, guardar el spec en `publicados/AAAA-MM-DD_tema.json` y agregar el video a `registro.json`
(son los únicos dos cambios que se suben a esta rama en una corrida normal):

```json
{"fecha": "2026-11-21", "serie": "CONCEPTO", "tema": "interes-compuesto",
 "titulo": "USD 100 por mes durante 30 años: ¿cuánto suman?", "cifra": "116.945",
 "spec": "publicados/2026-11-21_interes-compuesto.json",
 "fuentes": ["cálculo propio: 7% anual, aportes a fin de mes"]}
```

---

**Rehacer un video.** Con el spec guardado alcanza: copiarlo a la carpeta de trabajo y correr
los pasos de la sección 1. Para cambiar el nombre del canal en videos viejos, editar `brand`,
`brandLines` y la frase de cierre en cada spec y volver a filmar.

---

## 7. Mejorar con las métricas

Cuando haya datos del canal (YouTube Studio o vidIQ), anotar en `aprendizajes.md` qué
ganchos, series y duraciones retienen más, y aplicar eso al elegir el próximo tema.
Las que importan en Shorts: porcentaje que **eligió ver** frente a los que deslizaron,
**porcentaje promedio visto**, la curva de retención (dónde se van), suscriptores ganados
por video y compartidos.

---

Fuentes tipográficas: Anton e Inter, bajo SIL Open Font License 1.1 (ver `fonts/`).
Voz: Kokoro (modelo abierto, licencia Apache 2.0) mediante `kokoro-onnx`.
