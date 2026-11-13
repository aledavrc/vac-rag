# Plan de implementación — rapidfuzz y mejora de ingesta de fichas key-value

> Documento de trabajo derivado del análisis de `PLAN.org` (ADR-001/002/004) y del
> corpus real (`data/chunks.jsonl`). No modifica la pipeline por sí solo: describe
> las fases, tareas, archivos afectados y el modelo recomendado (pro/flash) para
> cada una.

## 1. Objetivo

1. Incorporar **`rapidfuzz`** para mejorar la normalización de claves de las fichas.
2. Mejorar la **ingesta de tablas key-value sin encabezados** de la sección de
   vacunas (fichas `6.1.1.2`–`6.1.1.24`).
3. Mantener y, si se justifica, ajustar **`rank-bm25`** en la recuperación.

## 2. Resumen de la investigación

### rank-bm25

- **Ya aplicado**: `BM25Okapi` en `src/vacuinfo/rag/retrieve.py` (índice en memoria)
  y fusionado con la búsqueda vectorial mediante RRF.
- **Beneficioso**: el corpus usa muchas siglas y valores exactos (`SPR`, `DPT`,
  `VPH`, `0,5 ml`, `2 a 8 °C`) que el embedding multilingüe no garantiza. El costo
  es casi nulo y es determinista.
- **Conclusión**: mantener. `BM25Okapi` basta para chunks ≤600 tokens; no se
  requiere `BM25Plus`/`BM25L`. Solo ajustar `bm25_k`/pesos RRF si la evaluación lo
  exige.

### rapidfuzz

- **No aplicado** hoy; el único fuzzy matching es `difflib.get_close_matches` en
  `normalize_field_name` (`src/vacuinfo/ingest/chunk.py`).
- **Posible**: librería C/C++ ligera, sin PyTorch, compatible con la imagen Docker.
- **Beneficioso**: `difflib` compara a nivel de caracteres y no maneja reordenamiento
  ni truncamiento. Ratios medidos contra claves canónicas (cutoff actual `0.82`
  las rechaza):

  | Clave rota (OCR) | Clave canónica | ratio `difflib` |
  |---|---|---|
  | `administracion via y sitio de` | `via y sitio de administracion` | 0.48 |
  | `simultaneo otras uso con vacunas` | `uso simultaneo con otras vacunas` | 0.75 |
  | `conservacion de` | `conservacion de la vacuna` | 0.75 |
  | `incas a` | `jeringas a utilizar` | 0.46 |
  | `post res` | `posibles efectos post vacunales` | 0.36 |

- **Dónde aplicarlo** (prioridad):
  1. **Ingesta — `normalize_field_name`** (alto impacto).
  2. **Consulta — `detect_vaccine`** (opcional, riesgo de falsos positivos;
     solo refuerzo de score, nunca filtro).

## 3. Diagnóstico de la ingesta actual

- 790 chunks: `texto` 197, `tabla_completa` 39, `tabla_fila` 267, `ficha_campo` 287.
- **29 de 287 `ficha_campo` (≈10 %) tienen clave no canónica**:
  - **14 `"Continuación"`**: celda de clave vacía; el valor continúa el campo
    anterior y hoy queda huérfano.
  - **13 claves OCR rotas**: `E`, `INCAS A`, `¿ POST RES`,
    `ADMINISTRACIÓN VIA Y SITIO DE`, `SIMULTÁNEO OTRAS USO CON VACUNAS`,
    `ESQUEMA DE Cc CIÓN VACUNACIO`, `CO CUBACIÓN`, `A STR ÓN DE -_`,
    `ÓN Ag NEO VACUNAS`, etc.
  - **1 clave fusionada**: `DOSIS (CANTIDAD) CONSERVACIÓN DE LA VACUNA`.
- **Fichas que caen en `tabla_completa` genérico** (pierden semántica key-value):
  Hepatitis B (p.14), Antineumocócica (p.24–25) y VPH (p.37) son de **3 columnas**
  (columna duplicada) y el código exige `width == 2`.
- **Sección/vacuna errónea** en p.24–25 (`Rotavirus` para la antineumocócica):
  el encabezado `6.1.1.10. VACUNA ANTINEUMOCÓCICA` no tiene `##` y `_is_heading`
  no lo detecta.

### Causas raíz

1. `normalize_field_name` no tolera reordenamiento/truncamiento/garble (`difflib`).
2. No hay fusión cross-página: cada página se chunkea sola.
3. Celdas de clave vacías generan "Continuación" en vez de concatenar al campo previo.
4. No se parten claves fusionadas en una celda.
5. Las fichas de 3 columnas no se detectan.
6. Detección de encabezados de sección frágil (solo `#…`/`ANEXO`).

## 4. Criterio general de modelo (pro vs flash)

- **flash**: tarea mecánica, bien especificada, verificable con tests, sin riesgo
  clínico. Editar código, regex y mapas una vez decidido el diseño.
- **pro**: decisión con ambigüedad, requiere inspeccionar el corpus o toca datos
  clínicos (veracidad). Diseñar reglas, elegir cutoffs, resolver claves ambiguas y
  redactar el ADR.
- **Patrón**: *pro diseña y revisa, flash ejecuta*.

## 5. Fases

### Fase 1 — Baseline medible (gold set + snapshot)

| #   | Tarea                                                                                                                                                | Modelo    | Por qué                                                          |
|-----|------------------------------------------------------------------------------------------------------------------------------------------------------|-----------|------------------------------------------------------------------|
| 1.1 | Definir gold set de fichas: 13 claves canónicas × ~20 fichas y resolver el mapeo de celdas rotas/ambiguas (`CO CUBACIÓN`, `TIPO INMUNIZACIÓN`, etc.) | **pro**   | Requiere leer páginas reales y decidir mapeos clínicos ambiguos. |
| 1.2 | Script que mida "% de claves canónicas por ficha" y snapshot del `hit@5` actual de `eval/preguntas.jsonl`                                            | **flash** | Conteo/JSON mecánico.                                            |

**Salida:** métrica antes/después para validar cada fase (método ADR-18).

### Fase 2 — rapidfuzz en `normalize_field_name` + fixes explícitos (tarea A)

| #   | Tarea                                                                                                                                  | Modelo    | Por qué                                                                                        |
|-----|----------------------------------------------------------------------------------------------------------------------------------------|-----------|------------------------------------------------------------------------------------------------|
| 2.1 | Añadir `rapidfuzz` a `pyproject.toml` (deps base)                                                                                      | **flash** | Una línea.                                                                                     |
| 2.2 | Sustituir `difflib.get_close_matches` por `rapidfuzz.process.extractOne` con `token_sort_ratio` (elegir scorer/cutoff ~80–85)          | **pro**   | Elegir contra los 29 casos reales y evitar falsos positivos (`COMPOSICIÓN` vs `CONSERVACIÓN`). |
| 2.3 | Ampliar `_OCR_FIELD_FIXES` con claves corruptas no ambiguas y regla para cortar prefijo de sección colado (`6.1.1.6 … TIPO DE VACUNA`) | **pro**   | Mapeo clínico determinista.                                                                    |
| 2.4 | Tests unitarios en `tests/test_chunk.py` para cada clave rota                                                                          | **flash** | Transcribir la tabla de casos.                                                                 |

**Archivos:** `pyproject.toml`, `src/vacuinfo/ingest/chunk.py`, `tests/test_chunk.py`.
**Aceptación:** las ~24 claves rotas pasan a canónicas; medir con Fase 1.

### Fase 3 — Detección de secciones y de fichas (tareas F + E)

| #   | Tarea                                                                                                                                 | Modelo    | Por qué                                                      |
|-----|---------------------------------------------------------------------------------------------------------------------------------------|-----------|--------------------------------------------------------------|
| 3.1 | Reconocer encabezados `6.1.1.N. VACUNA …` sin `##` (regex `\d+(\.\d+)+`)                                                              | **pro**   | Heurística frágil y específica del corpus (corrige p.24–25). |
| 3.2 | Generalizar detección de ficha: 1ª columna mayoritaria en `KNOWN_FIELDS`, aceptar `TIPO INMUNIZACIÓN`, soportar 3 columnas duplicadas | **pro**   | Cambia la rama `ficha_campo` vs `tabla_completa`.            |
| 3.3 | Tests con páginas 14, 24, 37 y 43 reales                                                                                              | **flash** | Replicar casos identificados.                                |

**Archivos:** `src/vacuinfo/ingest/chunk.py`, `src/vacuinfo/ingest/clean.py`,
`tests/test_chunk.py`.
**Aceptación:** fichas de 3 columnas y anti-VRS dejan de caer en `tabla_completa`.

### Fase 4 — Fusión cross-página + continuaciones (tareas B + C)

| #   | Tarea                                                                                                                                                            | Modelo    | Por qué                                                            |
|-----|------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------|--------------------------------------------------------------------|
| 4.1 | Diseñar la regla de fusión de tablas key-value consecutivas de la misma sección (sección igual + clave vacía o que no reinicia en `TIPO DE VACUNA` → concatenar) | **pro**   | El cambio más sutil; alinear con ADR-002 (fusión antes revertida). |
| 4.2 | Concatenar celdas con clave vacía al campo anterior (elimina 14 "Continuación")                                                                                  | **flash** | Edición mecánica con la regla fijada.                              |
| 4.3 | Tests para fichas partidas (SPR p.25–27, SR p.27–28) y continuaciones                                                                                            | **flash** | Casos ya mapeados.                                                 |

**Archivos:** `src/vacuinfo/ingest/chunk.py`, `tests/test_chunk.py`.
**Aceptación:** fichas partidas se reconstruyen; desaparecen los chunks huérfanos.

### Fase 5 — Claves fusionadas y pulido de 3 columnas (tarea D + cierre de E)

| #   | Tarea                                                                                 | Modelo    | Por qué                               |
|-----|---------------------------------------------------------------------------------------|-----------|---------------------------------------|
| 5.1 | Partir celdas con dos campos canónicos (`DOSIS (CANTIDAD) CONSERVACIÓN DE LA VACUNA`) | **pro**   | Decidir el corte sin perder el valor. |
| 5.2 | Marcar con `revisar=true` los casos ambiguos restantes                                | **flash** | Regla binaria.                        |

**Aceptación:** sin claves fusionadas; ambigüedades marcadas para revisión.

### Fase 6 — (Opcional) fuzzy en consulta: `detect_vaccine`

| #   | Tarea                                                                                         | Modelo    | Por qué                                         |
|-----|-----------------------------------------------------------------------------------------------|-----------|-------------------------------------------------|
| 6.1 | Fallback fuzzy (`partial_ratio`/`WRatio`) contra aliases, solo refuerzo de score, cutoff alto | **pro**   | Falsos positivos = vacuna equivocada (ADR-004). |
| 6.2 | Implementar y probar typos (`saramion`, `antipoliomielitica`)                                 | **flash** | Con cutoff fijado.                              |

**Recomendación:** posponer; beneficio marginal y riesgo no despreciable.

### Fase 7 — Evaluación y registro (ADR-006)

| #   | Tarea                                                                                | Modelo    | Por qué                                                            |
|-----|--------------------------------------------------------------------------------------|-----------|--------------------------------------------------------------------|
| 7.1 | Reconstruir índice (`make ingest`) y correr gold set + `eval`; comparar con baseline | **flash** | Ejecución determinista.                                            |
| 7.2 | Redactar ADR-006 con la plantilla §18 de `PLAN.org`                                  | **pro**   | Juicio y síntesis; justifica por qué la fusión se adopta esta vez. |

## 6. Resumen de modelo por fase

| Fase                                   | Modelo dominante                |
|----------------------------------------|---------------------------------|
| 1 Baseline                             | pro (gold set) + flash (script) |
| 2 rapidfuzz + fixes                    | pro (diseño) + flash (tests)    |
| 3 Secciones + detección ficha          | pro                             |
| 4 Fusión cross-página + continuaciones | pro (regla) + flash (código)    |
| 5 Claves fusionadas + pulido           | pro                             |
| 6 Fuzzy en consulta (opcional)         | pro                             |
| 7 Evaluación + ADR                     | flash (correr) + pro (ADR)      |

## 7. Orden de ejecución recomendado

1. Fase 1 (baseline validado).
2. Fase 2 (rapidfuzz + fixes; mayor impacto y menor riesgo).
3. Fase 3 (secciones + detección de ficha).
4. Fase 4 (fusión cross-página + continuaciones).
5. Fase 5 (claves fusionadas + pulido).
6. Fase 7 (evaluación + ADR-006).
7. Fase 6 solo si la evaluación muestra necesidad.

## 8. Riesgos y señales de revisión

- **Falsos positivos de rapidfuzz** entre campos parecidos (`COMPOSICIÓN` /
  `CONSERVACIÓN` / `CONSERVACIÓN DE LA VACUNA`): usar cutoff alto, `token_sort_ratio`
  y lista determinista para casos ambiguos.
- **Fusión indebida** de fichas o campos distintos: aplicar solo con sección igual
  y reinicio en `TIPO DE VACUNA`; marcar `revisar` cuando haya duda.
- **Datos clínicos**: nunca inferir ni completar valores (ADR-004); los casos
  dudosos se marcan, no se corrigen a ciegas.
- **Revisar la decisión** si el % de claves canónicas no sube o si el `hit@5`
  empeora respecto del baseline.

## 9. Prompts por fase (separados por modelo)

Convención: cada bloque es un **prompt autónomo** pensado para pegarse al inicio
de una sesión nueva. El modelo `pro` diseña/revisa; el `flash` ejecuta. Si una fase
tiene ambos, aplica primero el `pro` y luego el `flash` con el diseño ya aprobado.

| Fase | Sesión sugerida | Modelo | Prompt |
|---|---|---|---|
| 1 | A | pro → flash | Gold set → script de medición |
| 2 | B | pro → flash | Scorer/cutoff → implementación + tests |
| 3 | B (cont.) | pro → flash | Heurísticas → implementación + tests |
| 4 | C | pro → flash | Regla de fusión → implementación + tests |
| 5 | D | pro → flash | Corte de claves → implementación |
| 6 | D (opcional) | pro → flash | Fallback fuzzy → implementación |
| 7 | E | flash → pro | Correr eval → redactar ADR-006 |

### Fase 1 — Baseline medible

#### Prompt `pro` — diseñar el gold set

```text
Eres ingeniero de datos trabajando en el repositorio vacuinfo (RAG sobre la NTS
N° 246-MINSA/DGIESP-2026). Estás en modo implementación.

Contexto obligatorio: lee PLAN_IMPLEMENTACION.md (secciones 2–5) y PLAN.org
(ADR-001, ADR-002, ADR-004). La fuente de verdad del corpus es
data/chunks.jsonl y data/processed/*.clean.md.

Objetivo: definir el gold set de las fichas de vacuna para poder medir la mejora
de la ingesta key-value.

Tareas:
1. Localiza las fichas de vacuna 6.1.1.2 a 6.1.1.24 en data/processed/*.clean.md.
2. Usa las claves canónicas de KNOWN_FIELDS en src/vacuinfo/ingest/chunk.py
   (13 claves).
3. Crea eval/fichas_gold.jsonl con una línea por ficha:
   {"seccion","pagina","vacuna","claves":{clave_canonica: valor_esperado}}.
4. Resuelve explícitamente los mapeos ambiguos reales: "CO CUBACIÓN",
   "TIPO INMUNIZACIÓN", "¿ POST RES", "E", "INCAS A", "ESQUEMA".
5. Si un valor es dudoso, no lo infieras: usa null y "revisar": true.

Restricciones:
- No modifiques la pipeline ni data/chunks.jsonl.
- No corrijas valores clínicos por inferencia (ADR-004).
- Todo determinista y auditable.

Entregable: eval/fichas_gold.jsonl + tabla resumen (ficha → claves esperadas y
ambigüedades).
Criterio de aceptación: cada ficha tiene sus claves canónicas esperadas y las
ambigüedades quedan explícitas.
```

#### Prompt `flash` — script de medición

```text
Contexto: repositorio vacuinfo. Lee PLAN_IMPLEMENTACION.md (Fase 1) y
eval/fichas_gold.jsonl (ya existe).

Objetivo: crear un script que deje una foto reproducible del estado de la
ingesta antes de tocar código.

Tareas:
1. Crea scripts/medir_fichas.py (Python stdlib, sin dependencias nuevas).
2. Carga data/chunks.jsonl y eval/fichas_gold.jsonl.
3. Por ficha calcula: claves canónicas presentes / esperadas (%), y lista de
   claves no canónicas.
4. Imprime un resumen global, un desglose por página y el total de chunks con
   clave "Continuación".
5. Además ejecuta la evaluación de recuperación existente:
   .venv/bin/python -m vacuinfo.cli evaluar --archivo eval/preguntas.jsonl -k 5
   y reporta el Hit@5.
6. Guarda la salida en data/processed/baseline_fichas.txt.

Restricciones: no modifiques src/ ni data/chunks.jsonl; no reconstruyas el índice.
Entregable: scripts/medir_fichas.py + data/processed/baseline_fichas.txt.
Criterio: el script corre sin error y produce métricas comparables para las fases
siguientes.
```

### Fase 2 — rapidfuzz en normalize_field_name + fixes explícitos

#### Prompt `pro` — diseñar scorer/cutoff y mapa de fixes

```text
Contexto: repositorio vacuinfo, rama de trabajo de la Fase 2. Lee
PLAN_IMPLEMENTACION.md (Fase 2 y sección 3) y el código actual de
normalize_field_name en src/vacuinfo/ingest/chunk.py.

Objetivo: diseñar la sustitución de difflib por rapidfuzz y el mapa de
correcciones de claves OCR, antes de implementar.

Tareas:
1. Diseña la canonización con rapidfuzz.process.extractOne usando
   token_sort_ratio (evalúa también WRatio/token_set_ratio) contra
   _KNOWN_BY_NORMALIZED.
2. Propón el cutoff (rango 80–85) y justifícalo con los casos reales de
   PLAN_IMPLEMENTACION.md.
3. Añade a _OCR_FIELD_FIXES solo correcciones NO ambiguas: "E", "INCAS A",
   "¿ POST RES", "CONSERVACIÓN DE", "ADMINISTRACIÓN VIA Y SITIO DE",
   "SIMULTÁNEO OTRAS USO CON VACUNAS", "ESQUEMA".
4. Define la regla para cortar el prefijo de sección colado en la clave
   (ej. "6.1.1.6. VACUNA CONTRA TIPO DE VACUNA").
5. Verifica que COMPOSICIÓN no se confunda con CONSERVACIÓN y documenta el margen.

Restricciones: cambios deterministas; no tocar valores clínicos; no inventar
mapeos para claves ambiguas (esas se marcan para revisión).
Entregable: parche propuesto de src/vacuinfo/ingest/chunk.py + justificación de
scorer/cutoff.
Criterio: las 29 claves rotas de la sección 3 quedan resueltas o marcadas.
```

#### Prompt `flash` — implementar y probar

```text
Contexto: repositorio vacuinfo, Fase 2. Lee PLAN_IMPLEMENTACION.md (Fase 2) y el
diseño ya aprobado.

Tareas:
1. Añade "rapidfuzz>=3" a dependencies en pyproject.toml.
2. Implementa en src/vacuinfo/ingest/chunk.py el diseño aprobado: reemplaza
   difflib.get_close_matches por rapidfuzz.process.extractOne, amplía
   _OCR_FIELD_FIXES y añade el recorte de prefijo de sección.
3. Añade tests en tests/test_chunk.py para cada clave rota de la tabla de la
   Fase 2 (normalize_field_name).
4. Ejecuta .venv/bin/python -m pytest -q y
   .venv/bin/python -m ruff check src tests.

Restricciones: solo el alcance de la Fase 2; no toques la fusión cross-página ni
la detección de secciones.
Entregable: cambios + tests verdes + lint limpio.
Criterio: todas las claves objetivo canonizan correctamente y los tests previos
siguen pasando.
```

### Fase 3 — Detección de secciones y de fichas

#### Prompt `pro` — diseñar las heurísticas

```text
Contexto: repositorio vacuinfo, Fase 3. Lee PLAN_IMPLEMENTACION.md (Fase 3) y
src/vacuinfo/ingest/chunk.py y src/vacuinfo/ingest/clean.py.

Objetivo: diseñar la detección robusta de encabezados de sección y de fichas
key-value.

Tareas:
1. Diseña el reconocimiento de encabezados "6.1.1.N. VACUNA ..." aunque no tengan
   "##", sin confundirlos con párrafos ni referencias ("ver ítem 6.3").
2. Diseña la generalización de la rama ficha: 1ª columna mayoritariamente en
   KNOWN_FIELDS, aceptar "TIPO INMUNIZACIÓN", y soportar 3 columnas cuando las
   columnas 2..n son duplicados (HepB p.14, antineumocócica p.24–25, VPH p.37).
3. Define cómo evitar el bleed de sección/vacuna (caso Rotavirus en p.24–25).
4. Especifica casos límite y su comportamiento (tabla de 2 columnas que no es
   ficha, anexos, esquemas 6.2.x).

Restricciones: conservador; ante duda, no reclasificar como ficha.
Entregable: diseño + parche propuesto + lista de casos de prueba.
Criterio: las fichas de 3 columnas y anti-VRS dejan de caer en tabla_completa.
```

#### Prompt `flash` — implementar y probar

```text
Contexto: repositorio vacuinfo, Fase 3, diseño aprobado.

Tareas:
1. Implementa el diseño en src/vacuinfo/ingest/chunk.py (detección de encabezados
   y de fichas).
2. Añade tests en tests/test_chunk.py con las páginas 14, 24, 37 y 43 reales.
3. Verifica que las fichas de 2 columnas existentes siguen generando ficha_campo.
4. Ejecuta pytest y ruff.

Restricciones: no toques la fusión cross-página (Fase 4) ni el fuzzy (Fase 2, ya
hecho).
Entregable: cambios + tests verdes + lint limpio.
Criterio: sección y vacuna correctas en p.24–25; fichas de 3 columnas reconocidas.
```

### Fase 4 — Fusión cross-página + continuaciones

#### Prompt `pro` — diseñar la regla de fusión

```text
Contexto: repositorio vacuinfo, Fase 4. Lee PLAN_IMPLEMENTACION.md (Fase 4),
PLAN.org ADR-002 (la fusión se revirtió antes) y el estado actual de
src/vacuinfo/ingest/chunk.py.

Objetivo: diseñar una regla de fusión cross-página conservadora y auditable para
fichas key-value partidas.

Tareas:
1. Define la condición exacta de fusión: misma sección + (clave vacía o clave que
   no reinicia en "TIPO DE VACUNA").
2. Define qué hacer con valores que continúan de la página anterior
   (concatenación) y con filas cuyo campo anterior no existe.
3. Define cómo evitar fusionar dos fichas distintas o tablas de anexos.
4. Define cuándo marcar "revisar": true.
5. Especifica casos de prueba: SPR p.25–27, SR p.27–28, pentavalente p.18–19, y
   una ficha no partida como control negativo.

Restricciones: si la evidencia no es concluyente, preferir no fusionar (ADR-002).
Veracidad antes que cobertura.
Entregable: especificación de la regla + parche propuesto.
Criterio: las 14 "Continuación" se eliminan sin fusionar fichas distintas.
```

#### Prompt `flash` — implementar y probar

```text
Contexto: repositorio vacuinfo, Fase 4, regla aprobada.

Tareas:
1. Implementa la fusión y la concatenación de continuaciones en
   src/vacuinfo/ingest/chunk.py.
2. Añade tests en tests/test_chunk.py para los casos de la especificación,
   incluido el control negativo.
3. Ejecuta pytest y ruff.

Restricciones: solo Fase 4; no toques normalización de claves ni detección de
sección.
Entregable: cambios + tests verdes + lint limpio.
Criterio: cero chunks con clave "Continuación"; fichas partidas reconstruidas;
control negativo intacto.
```

### Fase 5 — Claves fusionadas y pulido de 3 columnas

#### Prompt `pro` — diseñar el corte de claves fusionadas

```text
Contexto: repositorio vacuinfo, Fase 5. Lee PLAN_IMPLEMENTACION.md (Fase 5) y
revisa el caso "DOSIS (CANTIDAD) CONSERVACIÓN DE LA VACUNA" en
data/chunks.jsonl.

Objetivo: definir cómo partir una celda de clave que contiene dos campos
canónicos y cómo marcar los casos ambiguos.

Tareas:
1. Define la regla de partición (orden de KNOWN_FIELDS, límites seguros).
2. Define cómo repartir el valor entre ambos campos sin perder texto.
3. Define qué casos quedan como revisar=true.
4. Revisa que el pulido de 3 columnas de la Fase 3 no deje duplicados de valor.

Restricciones: no inventar valores; si no se puede repartir con seguridad, marcar
revisión.
Entregable: especificación + parche propuesto.
Criterio: sin claves fusionadas; ambigüedades marcadas.
```

#### Prompt `flash` — implementar

```text
Contexto: repositorio vacuinfo, Fase 5, especificación aprobada.

Tareas:
1. Implementa en src/vacuinfo/ingest/chunk.py.
2. Añade tests en tests/test_chunk.py.
3. Ejecuta pytest y ruff.

Entregable: cambios + tests verdes + lint limpio.
Criterio: no quedan claves fusionadas en data/chunks.jsonl tras regenerar.
```

### Fase 6 — Fuzzy en consulta: detect_vaccine (opcional)

#### Prompt `pro` — diseñar fallback conservador

```text
Contexto: repositorio vacuinfo, Fase 6 (opcional). Lee PLAN_IMPLEMENTACION.md
(Fase 6), PLAN.org ADR-004 y detect_vaccine en src/vacuinfo/ingest/chunk.py.

Objetivo: diseñar un fallback fuzzy para typos en la pregunta, sin falsos
positivos.

Tareas:
1. Define scorer (partial_ratio/WRatio), cutoff alto y la condición de activación
   (solo si el match exacto falla).
2. Define que el resultado solo refuerza score en retrieve.py, nunca filtra.
3. Define pruebas con "saramion", "antipoliomielitica" y un caso que NO debe
   matchear.
4. Justifica por qué el beneficio supera el riesgo; si no, recomienda no
   implementarlo.

Entregable: decisión razonada (implementar o descartar) + diseño.
```

#### Prompt `flash` — implementar solo si se aprueba

```text
Contexto: repositorio vacuinfo, Fase 6, diseño aprobado.

Tareas:
1. Implementa el fallback en detect_vaccine
   (src/vacuinfo/ingest/chunk.py) y, si aplica, el refuerzo en
   src/vacuinfo/rag/retrieve.py.
2. Añade tests en tests/test_chunk.py.
3. Ejecuta pytest, ruff y .venv/bin/python -m vacuinfo.cli evaluar.

Entregable: cambios + tests verdes.
Criterio: typos esperados matchean; no aparecen falsos positivos en el eval.
```

### Fase 7 — Evaluación y ADR-006

#### Prompt `flash` — regenerar y medir

```text
Contexto: repositorio vacuinfo, Fase 7. Lee PLAN_IMPLEMENTACION.md.

Tareas:
1. Regenera chunks e índice:
   .venv/bin/python -m vacuinfo.cli ingestar --sin-ocr --sin-extraccion
   (o `chunks` + `indexar`).
2. Ejecuta .venv/bin/python scripts/medir_fichas.py y
   .venv/bin/python -m vacuinfo.cli evaluar --archivo eval/preguntas.jsonl -k 5.
3. Compara contra data/processed/baseline_fichas.txt y deja el resultado en
   data/processed/eval_final.txt.
4. Reporta: % de claves canónicas, nº de "Continuación", Hit@5 y nº de chunks por
   tipo.

Restricciones: no modifiques código en esta tarea.
Entregable: data/processed/eval_final.txt + tabla comparativa baseline vs final.
Criterio: métricas reproducibles y comparables.
```

#### Prompt `pro` — redactar ADR-006

```text
Contexto: repositorio vacuinfo, Fase 7. Lee PLAN_IMPLEMENTACION.md, PLAN.org §18
(plantilla ADR) y los resultados en data/processed/eval_final.txt.

Objetivo: registrar la decisión de forma que otra persona pueda reproducirla.

Tareas:
1. Redacta ADR-006 con: Contexto, Opciones (incluye "no cambiar"), Criterios,
   Evidencia (métricas antes/después), Decisión, Consecuencias, Revisar si.
2. Explica por qué la fusión se adopta esta vez y deja de ser el caso revertido de
   ADR-002.
3. Añade el ADR a PLAN.org (sección 18.3) y actualiza el estado en README.org si
   corresponde.
4. No cambies código en esta tarea.

Entregable: ADR-006 redactado y ubicado en PLAN.org.
Criterio: incluye evidencia numérica y una señal de revisión concreta.
```
