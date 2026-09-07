import sys
from pathlib import Path
from detection.paddleocr_detect import PaddleOCRDetector
from preprocessing.ingestion import Ingestion

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ingestion = Ingestion()
detector = PaddleOCRDetector(use_gpu=False)

for gcn in ['GCN_1', 'GCN_2', 'GCN_3']:
    print('=' * 30 + ' ' + gcn + ' ' + '=' * 30)
    for fname in ['MT.png', 'MS.png']:
        img_path = Path('input') / gcn / fname
        if not img_path.exists():
            continue
        imgs = ingestion.load(str(img_path))
        res = detector.detect(imgs[0])
        print(f'\n--- {gcn}/{fname} ({len(res)} text lines) ---')
        for i, item in enumerate(res):
            t = item['text']
            c = item['confidence']
            print(f'  [{i:2d}] ({c:.2f}) {t}')
