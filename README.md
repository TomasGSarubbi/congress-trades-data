# congress-trades-data

Pipeline que baja **todos los días** las operaciones bursátiles declaradas por
los miembros del Congreso de EE.UU. (STOCK Act) desde las **fuentes oficiales**:

- Senado: [efdsearch.senate.gov](https://efdsearch.senate.gov) (PTRs electrónicos, HTML)
- Cámara: [disclosures-clerk.house.gov](https://disclosures-clerk.house.gov) (índice anual + PDFs de PTRs)

Un GitHub Action corre cada mañana (09:30 hora Argentina), scrapea los reportes
presentados en los últimos 7 días y commitea los resultados a `data/`:

| Archivo | Contenido |
|---|---|
| `data/transactions.json` | Rolling de los últimos 120 días (por fecha de presentación) |
| `data/latest.json` | Solo las transacciones nuevas desde la corrida anterior |
| `data/meta.json` | Timestamp, conteos y errores de la última corrida |

## Setup (una sola vez)

```bash
cd congress-trades-data
git init && git add -A && git commit -m "init"
gh repo create congress-trades-data --public --source=. --push
```

Después, en GitHub → Actions → **Fetch congressional trades** → *Run workflow*
para la primera corrida manual. Las siguientes salen solas todos los días.

> El repo debe ser **público** para que los datos se puedan leer por
> `raw.githubusercontent.com` sin token.

## Correr local

```bash
pip install -r requirements.txt
python scraper/run.py
```

## Notas y límites

- Los congresistas tienen hasta **45 días** para declarar una operación:
  esto es transparencia con retraso, no señal en tiempo real.
- Los reportes presentados **en papel** (escaneados) se omiten (~son minoría).
- Montos: la ley solo exige **rangos** ($1,001–$15,000, etc.), no cifras exactas.
- Datos = dominio público (registros del gobierno de EE.UU.).
