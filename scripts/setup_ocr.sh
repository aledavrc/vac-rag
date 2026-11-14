#!/usr/bin/env bash
# Opcional: solo se necesita con VACUINFO_OCR_ENGINE=tesseract_cli.
# El OCR por defecto (RapidOCR/ONNX) no requiere tessdata.
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p models/tessdata
size=0
if [[ -f models/tessdata/spa.traineddata ]]; then
  # `wc -c` existe en Linux, macOS y Git Bash (stat cambia de sintaxis).
  size=$(wc -c < models/tessdata/spa.traineddata | tr -d '[:space:]')
fi
if (( size < 5000000 )); then
  echo "Descargando spa.traineddata (tessdata_best)..."
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL -o models/tessdata/spa.traineddata \
      https://github.com/tesseract-ocr/tessdata_best/raw/main/spa.traineddata
  elif command -v wget >/dev/null 2>&1; then
    wget -qO models/tessdata/spa.traineddata \
      https://github.com/tesseract-ocr/tessdata_best/raw/main/spa.traineddata
  else
    echo "Se necesita curl o wget para descargar el modelo." >&2
    exit 1
  fi
fi

# OCRmyPDF necesita configs/, tessconfigs/ y pdf.ttf junto al modelo de idioma.
# Rutas habituales en Linux (distro y snap), macOS (Homebrew) y TESSDATA_PREFIX.
for dir in \
  /usr/share/tessdata \
  /usr/share/tesseract-ocr/*/tessdata \
  /opt/homebrew/share/tessdata \
  /usr/local/share/tessdata \
  "${TESSDATA_PREFIX:-}"; do
  [[ -n "$dir" && -d "$dir" ]] || continue
  if [[ -d "$dir/configs" ]]; then
    cp -r "$dir/configs" "$dir/tessconfigs" "$dir/pdf.ttf" models/tessdata/ 2>/dev/null || true
    cp "$dir/osd.traineddata" models/tessdata/ 2>/dev/null || true
    break
  fi
done

echo "Tessdata listo en models/tessdata"
