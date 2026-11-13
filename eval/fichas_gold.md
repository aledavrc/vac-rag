# Gold set de fichas de vacuna (Fase 1 — tarea 1.1)

> Fuente de verdad: `data/processed/8265031-nts-n-246-minsa-digiesp-2026-parte-1.clean.md`
> (secciones `6.1.1.2`–`6.1.1.24`). No se modificó la pipeline ni `data/chunks.jsonl`.
>
> Schema por línea (JSONL): `{"seccion", "pagina", "vacuna", "claves"}`; `claves`
> mapea **clave canónica** (13 de `KNOWN_FIELDS` en `src/vacuinfo/ingest/chunk.py`)
> → valor esperado. `revisar: true` + valor `null` = valor dudoso, **no inferido**
> (ADR-004).

## 1. Claves canónicas (13)

1. `TIPO DE VACUNA`
2. `DESCRIPCIÓN`
3. `COMPOSICIÓN`
4. `PRESENTACIÓN`
5. `INDICACIÓN`
6. `ESQUEMA DE VACUNACIÓN`
7. `DOSIS (CANTIDAD)`
8. `CONSERVACIÓN DE LA VACUNA`
9. `VÍA Y SITIO DE ADMINISTRACIÓN`
10. `JERINGAS A UTILIZAR`
11. `POSIBLES EFECTOS POST-VACUNALES`
12. `CONTRAINDICACIÓN`
13. `USO SIMULTÁNEO CON OTRAS VACUNAS`

## 2. Mapeos ambiguos resueltos (obligatorios de la tarea)

| Clave OCR rota (fuente) | Clave canónica | Ficha | Evidencia / decisión |
|---|---|---|---|
| `CO CUBACIÓN` | `ESQUEMA DE VACUNACIÓN` | 6.1.1.23 Meningococo | Valor "02 dosis: a los 13 meses y 15 meses" = esquema. |
| `TIPO INMUNIZACIÓN` | `TIPO DE VACUNA` | 6.1.1.24 Anticuerpo monoclonal | Es una inmunización, no una vacuna; el campo "tipo" ocupa la casilla de `TIPO DE VACUNA`. |
| `¿ POST RES` | `POSIBLES EFECTOS POST-VACUNALES` | 6.1.1.18 HVA | Valor "Las reacciones en cuestión son leves…" = efectos post-vacunales. |
| `E` | `CONSERVACIÓN DE LA VACUNA` | 6.1.1.8 APO | Valor "Luego de la apertura del frasco se puede conservar 4 semanas." es conservación (nota: falta `+2°C a +8°C` en el OCR). |
| `INCAS A` | `JERINGAS A UTILIZAR` | 6.1.1.14 AMA | Valor "Para administrar: jeringa descartable de 1ml…" = jeringas. |
| `ESQUEMA` | `ESQUEMA DE VACUNACIÓN` | 6.1.1.24 Anticuerpo monoclonal | Valor "En recién nacidos de madres no vacunadas…" = esquema. |

## 3. Mapeos adicionales (resto de claves OCR rotas del corpus)

| Clave OCR rota | Clave canónica | Ficha(s) |
|---|---|---|
| `IPO DE VACUNA` | `TIPO DE VACUNA` | 6.1.1.9 Rotavirus |
| `TIPO DE VACUNA -` / `TIPO DE VACUNA.` | `TIPO DE VACUNA` | 6.1.1.11 SPR / 6.1.1.17 Tdap |
| `DESCRIPCION` / `A DESCRIPCION` | `DESCRIPCIÓN` | 6.1.1.13 Varicela / 6.1.1.23 Meningococo |
| `La COMPOSICIÓN` / `> COMPOSICIÓN` | `COMPOSICIÓN` | 6.1.1.23 / 6.1.1.7 |
| `PRESENT ACIÓN` | `PRESENTACIÓN` | 6.1.1.7 IPV |
| `, INDICACIÓN` / `: INDICACIÓN` / `b INDICACIÓN` / `e INDICACIÓN` | `INDICACIÓN` | 6.1.1.23 / 6.1.1.16 / 6.1.1.2 / 6.1.1.20 |
| `ESQUEMA DE VACUNACION` / `ESQUEMA DE Cc CIÓN VACUNACIO` | `ESQUEMA DE VACUNACIÓN` | 6.1.1.2, 6.1.1.11 / 6.1.1.14 AMA |
| `CONSERVACIÓNDE LA VACUNA` / `CONSERVACIÓN DE` / `CONSERVACIÓN DE -` / `CONSERVACION DE LA VACUNA` | `CONSERVACIÓN DE LA VACUNA` | 6.1.1.11, 6.1.1.17 / 6.1.1.3 / 6.1.1.7 / 6.1.1.5 |
| `VÍA Y sitio DE ADMINISTRACIÓN` / `vía Y sITIO DE ADMINISTRACIÓN -` / `ADMINISTRACIÓN VIA Y SITIO DE` / `VÍA NTE y Dr _-` / `A STR ÓN DE -_` / `VÍA Y SITIO DE ADMINISTRACIÓN *` | `VÍA Y SITIO DE ADMINISTRACIÓN` | 6.1.1.11 / 6.1.1.12 / 6.1.1.8 / 6.1.1.10 / 6.1.1.23 / 6.1.1.6 |
| `POSIBLES EFECTOS POST- VACUNALES` / `POSTVACUNALES` / `POST VACUNALES.` / `POSIBLES EFECTOS POST-VACUNALES .` / `- E.` | `POSIBLES EFECTOS POST-VACUNALES` | 6.1.1.13 / 6.1.1.21 / 6.1.1.16 / 6.1.1.10 / 6.1.1.6 |
| `CONTRAINDIC ACIÓN` / `CONTRAINDICACION` / `Z CONTRAINDICACIÓN` / `CONTRAINDICACIÓN &#124;` | `CONTRAINDICACIÓN` | 6.1.1.10 / 6.1.1.21, 6.1.1.22, 6.1.1.24 / 6.1.1.23 / 6.1.1.12 |
| `USO SIMULTANEO CON OTRAS VACUNAS` / `SIMULTÁNEO OTRAS USO CON VACUNAS` / `USO SsiIMULTÁNEO…` / `USO IMULTÁNEO…` / `ÓN Ag NEO VACUNAS` / `CON OTRAS VACUNAS` / `USO SIMULTÁNEO CON OTRAS VAGUNAS` | `USO SIMULTÁNEO CON OTRAS VACUNAS` | 6.1.1.6 / 6.1.1.7, 6.1.1.20 / 6.1.1.12 / 6.1.1.10 / 6.1.1.23 / 6.1.1.24 / 6.1.1.14 |

Claves **fusionadas en una celda** (Fase 5):

| Celda | Resolución |
|---|---|
| `DOSIS (CANTIDAD) CONSERVACIÓN DE LA VACUNA` | `DOSIS (CANTIDAD)` = "0.5 ml." + `CONSERVACIÓN DE LA VACUNA` = "+2°C a +8°C Frasco abierto: su uso es inmediato" (6.1.1.4). |
| `CONSERVACIÓN DE | LA VACUNA VÍA Y SITIO DE ADMINISTRACIÓN` | `CONSERVACIÓN DE LA VACUNA` (cierre) + `VÍA Y SITIO DE ADMINISTRACIÓN` (6.1.1.3). |
| `6.1.1.6. VACUNA CONTRA TIPO DE VACUNA` | Prefijo de sección colado en la clave → sección `6.1.1.6. VACUNA CONTRA HAEMOPHILUS INFLUENZAE TIPO B (Hib)` + clave `TIPO DE VACUNA` (6.1.1.6). |

## 4. Valores dudosos → `null` + `revisar: true` (no inferidos)

| Ficha | Clave dudosa | Motivo |
|---|---|---|
| 6.1.1.12 SR | `DOSIS (CANTIDAD)` | OCR ilegible (`**`); no se infiere. |
| 6.1.1.16 dT adulto | `DOSIS (CANTIDAD)` | OCR ilegible (`5 MI`); no se infiere. |
| 6.1.1.16 dT adulto | `CONSERVACIÓN DE LA VACUNA` | Temperatura de conservación ilegible en OCR; solo es legible "…conservar 4 semanas". |
| 6.1.1.17 Tdap | `DOSIS (CANTIDAD)` | Celda vacía en el OCR; no se infiere. |
| 6.1.1.23 Meningococo | `DOSIS (CANTIDAD)` | OCR ilegible (`o5m!`); no se infiere. |

## 5. Campos ausentes de la fuente (no esperados)

| Ficha | Campo ausente | Motivo |
|---|---|---|
| 6.1.1.8 APO (oral) | `JERINGAS A UTILIZAR` | Vacuna oral; la fuente no lista jeringas. |
| 6.1.1.9 Rotavirus (oral) | `JERINGAS A UTILIZAR` | Vacuna oral; la fuente no lista jeringas. |
| 6.1.1.20 Influenza | `DOSIS (CANTIDAD)` | La dosis se describe dentro de `ESQUEMA DE VACUNACIÓN`; no hay fila propia. |

## 6. Resumen por ficha

| Sección | Página | Vacuna | # claves | Dudosas |
|---|---|---|---|---|
| 6.1.1.2 Hepatitis B (HvB) | 14 | Hepatitis B | 13 | — |
| 6.1.1.3 Hexavalente (DPT-HvB-Hib-IPV) | 16 | Hexavalente | 13 | — |
| 6.1.1.4 Pentavalente (DPT-HvB-Hib) | 17 | Pentavalente | 13 | — |
| 6.1.1.5 DT pediátrico | 19 | DT pediátrico | 13 | — |
| 6.1.1.6 Hib | 20 | Hib | 13 | — |
| 6.1.1.7 IPV | 21 | IPV | 13 | — |
| 6.1.1.8 APO | 22 | APO/VOP | 12 | — |
| 6.1.1.9 Rotavirus | 23 | Rotavirus | 12 | — |
| 6.1.1.10 Antineumocócica | 24 | Neumococo | 13 | — |
| 6.1.1.11 SPR | 25 | SPR | 13 | — |
| 6.1.1.12 SR | 27 | SR | 13 | DOSIS (CANTIDAD) |
| 6.1.1.13 Varicela | 28 | Varicela | 13 | — |
| 6.1.1.14 AMA | 29 | Fiebre amarilla | 13 | — |
| 6.1.1.15 DPT | 31 | DTP | 13 | — |
| 6.1.1.16 dT adulto | 32 | dT adulto | 13 | DOSIS (CANTIDAD), CONSERVACIÓN DE LA VACUNA |
| 6.1.1.17 Tdap | 33 | Tdap | 13 | DOSIS (CANTIDAD) |
| 6.1.1.18 HVA | 34 | Hepatitis A | 13 | — |
| 6.1.1.19 VPH | 35 | VPH | 13 | — |
| 6.1.1.20 Influenza | 37 | Influenza | 12 | — |
| 6.1.1.21 VRS | 39 | VRS | 13 | — |
| 6.1.1.22 Hexavalente VIH | 40 | Hexavalente VIH | 13 | — |
| 6.1.1.23 Meningococo | 42 | Meningococo | 13 | DOSIS (CANTIDAD) |
| 6.1.1.24 Anticuerpo monoclonal VRS | 43 | Nirsevimab | 13 | — |

**Totales:** 23 fichas · 296 claves esperadas · 5 valores dudosos (`null`) en 4 fichas.
