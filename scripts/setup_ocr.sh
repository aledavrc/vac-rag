#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p models/tessdata
size=0
if [[ -f models/tessdata/spa.traineddata ]]; then
  size=$(stat -c%s models/tessdata/spa.traineddata 2>/dev/null || echo 0)
fi
if (( size < 5000000 )); then
  echo "Descargando spa.traineddata (tessdata_best)..."
  curl -fsSL -o models/tessdata/spa.traineddata \
    https://github.com/tesseract-ocr/tessdata_best/raw/main/spa.traineddata
fi

# OCRmyPDF necesita configs/, tessconfigs/ y pdf.ttf junto al modelo de idioma.
for dir in /usr/share/tessdata /usr/share/tesseract-ocr/*/tessdata; do
  if [[ -d "$dir/configs" ]]; then
    cp -r "$dir/configs" "$dir/tessconfigs" "$dir/pdf.ttf" models/tessdata/ 2>/dev/null || true
    cp "$dir/osd.traineddata" models/tessdata/ 2>/dev/null || true
    break
  fi
done

echo "Tessdata listo en models/tessdata"
