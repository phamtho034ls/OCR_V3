import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    import torch
except Exception:
    pass

import glob
from detection.paddleocr_detect import PaddleOCRDetector
from preprocessing.ingestion import Ingestion
from extraction.template_classifier import TemplateClassifier

detector = PaddleOCRDetector(use_gpu=False)
ingestion = Ingestion()
classifier = TemplateClassifier()

files = ["input/Screenshot 2026-08-17 155533.png", "input/Screenshot 2026-08-17 155543.png"]
for f in files:
    fname = Path(f).name
    print("=" * 70)
    print(f"FILE: {fname}")
    imgs = ingestion.load(f)
    if not imgs:
        print("Could not load image.")
        continue
    ocr_results = detector.detect(imgs[0])
    tpl = classifier.classify(ocr_results)
    print(f"Detected {len(ocr_results)} text boxes | Classified as: {tpl}")
    print("Detected Texts:")
    for idx, item in enumerate(ocr_results, 1):
        print(f"  {idx:2d}. [{item['confidence']:.2f}] {item['text']}")
