# Preguntas de evaluación — VacuInfo

- **Corpus:** NTS N° 246-MINSA/DGIESP-2026 (140 páginas, 807 chunks).
- **Índice:** `data/index/chroma` + BM25, fusión RRF.
- **Fecha de la prueba:** 2026-11-12.
- **Conjunto:** 20 preguntas dentro de alcance + 5 fuera de alcance.
- **Comando de recuperación:**

```bash
.venv/bin/python -m vacuinfo.cli evaluar --archivo eval/preguntas.jsonl -k 5
```

## Resumen

| Métrica | Resultado |
|---|---|
| Hit@5 (fuente correcta en el top 5) | **20/20 = 1,00** |
| Respuestas extractivas con cita verificable | **20/20** |
| Abstención fuera de alcance, modo extractivo | **2/5** |
| Abstención fuera de alcance, con LLM disponible | **5/5** |

> En modo extractivo la salvaguarda de alcance es léxica: solo comprueba que algún término
> significativo de la pregunta aparezca en los fragmentos recuperados. Por eso las preguntas
> fuera de alcance que contienen palabras presentes en la norma (“diabetes”, “Chile”, “años”)
> reciben un fragmento irrelevante en vez de abstenerse. Con el LLM configurado, el prompt
> restrictivo sí logra la abstención en las 5 preguntas.

## Preguntas dentro de alcance

| # | Tipo | Pregunta | Respuesta esperada | Pág. | Sección | Palabras clave | Hit@5 |
|---:|---|---|---|---:|---|---|---|
| 1 | Normativa | ¿Cuál es la finalidad de la NTS 246? | Contribuir a disminuir la morbimortalidad causada por enfermedades inmunoprevenibles, protegiendo la vida y la salud de la población por curso de vida mediante las inmunizaciones. | 1 | FINALIDAD | morbimortalidad, inmunoprevenibles | OK |
| 2 | Normativa | ¿Cuál es el objetivo general de la norma? | Establecer el esquema nacional de inmunizaciones para la población por curso de vida. | 1 | 2.1 Objetivo General | esquema nacional, curso de vida | OK |
| 3 | Ficha | ¿Cuál es la composición de la vacuna antipoliomielítica oral? | Una dosis de 2 gotas contiene virus de polio (Sabin) cultivado en células de riñón de mono, tipos 1 y 3, neomicina 15 mcg y MgCl₂ como estabilizante. | 22 | 6.1.1.8 | poliovirus, Sabin, neomicina | OK |
| 4 | Ficha | ¿Qué hacer si un niño regurgita la vacuna antipoliomielítica oral? | Se administra 1 dosis de reemplazo. | 22 | 6.1.1.8 | dosis de reemplazo, regurgita | OK |
| 5 | Caso especial | ¿Cuál es el esquema de vacunación de la Tdap en gestantes? | Una dosis de Tdap entre las 20 y 36 semanas de gestación, en cada gestación. | 34 | 6.1.1.17 | Tdap, 20 a 36 semanas, gestación | OK |
| 6 | Ficha | ¿Cuál es la composición de la vacuna contra la hepatitis A? | Virus de la hepatitis A inactivado (cepa HM175): 720 unidades de ELISA, adsorbido en hidróxido de aluminio hidratado Al³⁺ 0,25 mg; residuo de sulfato de neomicina. | 34 | 6.1.1.18 | cepa HM175, hepatitis A, aluminio | OK |
| 7 | Anexo / tabla | ¿Qué tasa de linfadenitis supurativa se asocia a la vacuna BCG? | 100 a 1000 casos por 1 000 000 de dosis; aparece entre 2 y 6 meses. | 98 | ANEXO 8 | linfadenitis, BCG, 100 a 1000 | OK |
| 8 | Anexo / tabla | ¿Cuánto tarda en aparecer la anafilaxia asociada a la DPT? | De 0 a 1 hora; tasa de 20 por 1 000 000 de dosis. | 98 | ANEXO 8 | anafilaxia, DPT, 0 a 1 hora | OK |
| 9 | Anexo / tabla | ¿Qué consecuencia tiene una inyección no estéril? | Infección: absceso localizado en el sitio de inyección, sepsis, síndrome de choque tóxico o muerte; también infección transmitida por sangre (hepatitis o VIH). | 100 | ANEXO 9 | inyección no estéril, infección, sepsis | OK |
| 10 | Dato exacto | ¿Cuál es la dosis de la vacuna contra el rotavirus? | 1,5 ml. | 23 | 6.1.1.9 | dosis, rotavirus, 1,5 ml | OK |
| 11 | Dato exacto | ¿Cuál es la dosis de la vacuna Tdap? | 0,5 ml (frasco monodosis). El campo “DOSIS (CANTIDAD)” está ilegible en el OCR; la presentación de la ficha indica 0,5 ml. | 34 | 6.1.1.17 | Tdap, dosis, 0,5 ml | OK |
| 12 | Dato exacto / ficha | ¿A qué temperatura se conserva la vacuna contra la fiebre amarilla y cuánto dura una vez reconstituida? | De +2 °C a +8 °C. Una vez reconstituida, debe usarse dentro de 6 horas. | 30 | 6.1.1.14 | fiebre amarilla, conservación, 6 horas | OK |
| 13 | Dato exacto / ficha | ¿Cuál es la vía y el sitio de administración de la vacuna contra la hepatitis B en adultos? | Intramuscular, en la región deltoides (parte superior de la cara lateral externa del brazo). | 16 | 6.1.1.2 | hepatitis B, intramuscular, deltoides | OK |
| 14 | Ficha | ¿Cuál es la composición de la vacuna combinada pentavalente? | Cada dosis de 0,5 ml contiene toxoide diftérico <25 Lf (>30 UI), toxoide tetánico ≥2,5 Lf (≥40 UI), B. pertussis de célula entera <16 UO (≥4 UI), HBsAg 10 mcg, PRP-Hib conjugado con toxoide tetánico 10 mcg, fosfato de aluminio <1,25 mg y tiomersal 0,005 %. | 18 | 6.1.1.4 | pentavalente, toxoide diftérico, HBsAg | OK |
| 15 | Caso especial | ¿Qué vacunas se aplican durante el embarazo según el esquema prenatal? | Tdap entre 20 y 36 semanas; VRS entre 32 y 36 semanas; influenza una dosis anual en cualquier edad gestacional; hepatitis B si no hay esquema o está incompleto. | 45 | 6.2.1 | prenatal, Tdap, VRS, influenza, hepatitis B | OK |
| 16 | Caso especial | ¿Qué vacuna recibe el recién nacido con VIH asintomático? | Una dosis de BCG. En el VIH sintomático, la vacunación se realiza bajo evaluación médica. | 48 | 6.3.1 | VIH, recién nacido, BCG | OK |
| 17 | Caso especial | ¿Qué vacunas debe recibir el personal de salud? | HVB (3 dosis: al contacto, al mes y a los 6 meses), influenza anual, antiamarílica dosis única, neumococo dosis única, dT (3 dosis) y Tdap en zonas con brote de tos ferina; SR/SPR según riesgo epidemiológico. | 53 | 6.3.4 | personal de salud, HVB, influenza | OK |
| 18 | Anexo | ¿Existe contraindicación para administrar varias vacunas simultáneamente? | No. No existe contraindicación para la administración simultánea de múltiples vacunas rutinariamente recomendadas; no altera la producción de anticuerpos ni aumenta las reacciones post-vacunales. | 79 | ANEXO 1 | administración simultánea, contraindicación | OK |
| 19 | Anexo | ¿Cuánto tiempo dura un frasco multidosis abierto según la política de frascos abiertos? | Los frascos líquidos multidosis (APO, DPT, dT pediátrica, dT adulto, influenza pediátrica) duran 28 días, rotulados con fecha y hora de apertura. Los liofilizados reconstituidos (BCG, SPR, SR, antiamarílica) se usan hasta 6 horas. En trabajo extramural se descartan al terminar la jornada. | 82 | ANEXO 3 | frasco multidosis, 28 días, 6 horas | OK |
| 20 | Anexo | ¿Es necesario reiniciar el esquema de vacunación si se interrumpe? | No. Se continúa con las dosis faltantes sin considerar el tiempo transcurrido; no es necesario reiniciar el esquema en ninguna circunstancia. | 80 | ANEXO 2 | interrupción, dosis de rescate, no reiniciar | OK |

## Preguntas fuera de alcance

| # | Pregunta | Motivo | Resultado esperado | Extractivo | LLM |
|---:|---|---|---|---|---|
| 21 | ¿Cuál es el precio de la vacuna contra el VPH? | Información comercial, no contenida en la norma. | Abstención. | Abstención | Abstención |
| 22 | ¿Qué dice la norma sobre la vacuna contra el ébola? | Vacuna no incluida en el esquema ni en el corpus. | Abstención. | Abstención | Abstención |
| 23 | ¿Cuál es el tratamiento recomendado para la diabetes tipo 2? | Recomendación clínica ajena a la norma; “diabetes” aparece como comorbilidad. | Abstención. | Responde con un fragmento irrelevante | Abstención |
| 24 | ¿Qué vacunas incluye el calendario de vacunación de Chile? | Otra norma/país; “Chile” aparece en una mención de la Semana Andina. | Abstención. | Responde con un fragmento irrelevante | Abstención |
| 25 | ¿Cuánto paracetamol se le da a un niño de 5 años? | Recomendación clínica y de dosificación no vacunal; “años” aparece en el corpus. | Abstención. | Responde con un fragmento irrelevante | Abstención |

## Observaciones

- Las 20 preguntas dentro de alcance recuperan la página y sección esperadas en el top 5.
- Las respuestas extractivas incluyen `*Fuente: [NTS N° 246-MINSA/DGIESP-2026, p. …, sección …]*`.
- La pregunta 11 depende de un campo OCR ilegible; se validó con la presentación de la ficha
  (0,5 ml) y sigue marcada como punto de revisión, igual que en `data/processed/revision.md`.
- Las preguntas 23–25 no se abstienen en modo extractivo porque la comprobación de alcance solo
  busca coincidencia de términos. Es el principal punto a mejorar si se quiere garantizar la
  abstención sin LLM.
- La prueba con LLM se hizo contra el proveedor configurado en `.env`; una corrida posterior
  devolvió `402 Payment Required`, por lo que las métricas de respuesta se reportan en modo
  extractivo y la abstención con LLM se limita a la corrida que sí completó.
