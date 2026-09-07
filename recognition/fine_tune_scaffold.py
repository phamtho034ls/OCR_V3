"""
Script scaffold để fine-tune mô hình VietOCR trên dữ liệu sổ đỏ/sổ hồng.

# ============================================================
# HƯỚNG DẪN SỬ DỤNG
# ============================================================
# Khi bạn đã có dữ liệu gán nhãn thực, thực hiện các bước sau:
#
# 1. CHUẨN BỊ DỮ LIỆU:
#    - Tạo thư mục dữ liệu với cấu trúc:
#        data_dir/
#            images/       ← ảnh crop từng dòng văn bản
#                0001.jpg
#                0002.jpg
#                ...
#            train.csv     ← nhãn tập train
#            val.csv       ← nhãn tập validation
#            test.csv      ← nhãn tập test (tùy chọn)
#
#    - Định dạng CSV (không có header):
#        images/0001.jpg,Số thửa đất
#        images/0002.jpg,123
#        ...
#
# 2. CHẠY FINE-TUNE:
#    python fine_tune_scaffold.py \
#        --data-dir ./data \
#        --save-dir ./checkpoints \
#        --base-model vgg_transformer \
#        --epochs 20
#
# 3. ĐÁNH GIÁ:
#    Sau khi train xong, kết quả CER/WER sẽ in ra console.
#
# ============================================================
# TODO: Thêm dữ liệu thật rồi chạy script này
# ============================================================

import argparse
import csv
import logging
import os
from pathlib import Path
from typing import List, Tuple, Optional

import torch
from torch.utils.data import DataLoader, Dataset

# Thiết lập logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================
# Dataset
# ============================================================

class FineTuneDataset(Dataset):
    """
    Dataset để fine-tune VietOCR trên ảnh crop + nhãn văn bản.

    Đọc dữ liệu từ file CSV với định dạng:
        <đường_dẫn_ảnh_tương_đối>,<nhãn_văn_bản>

    Ví dụ CSV:
        images/0001.jpg,Số thửa đất
        images/0002.jpg,Tờ bản đồ số

    Attributes:
        data_dir: Thư mục gốc chứa dữ liệu.
        samples: List các tuple (image_path, label).
        transform: Transform PIL (nếu có).
    """

    def __init__(
        self,
        csv_file: str,
        data_dir: str,
        transform=None,
    ) -> None:
        """
        Khởi tạo FineTuneDataset.

        Args:
            csv_file: Đường dẫn tuyệt đối đến file CSV nhãn.
            data_dir: Thư mục gốc, các đường dẫn trong CSV là tương đối so với đây.
            transform: Transform tùy chọn áp dụng lên PIL Image.

        Raises:
            FileNotFoundError: Nếu csv_file không tồn tại.
            ValueError: Nếu CSV không đúng định dạng (thiếu cột).
        """
        csv_path = Path(csv_file)
        if not csv_path.exists():
            raise FileNotFoundError(f"Không tìm thấy file CSV: {csv_file}")

        self.data_dir = Path(data_dir)
        self.transform = transform
        self.samples: List[Tuple[Path, str]] = []

        # Đọc CSV
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row_num, row in enumerate(reader, start=1):
                if len(row) < 2:
                    logger.warning(
                        "Dòng %d trong CSV không đủ cột, bỏ qua: %s", row_num, row
                    )
                    continue
                image_rel_path = row[0].strip()
                label = row[1].strip()
                full_image_path = self.data_dir / image_rel_path

                if not full_image_path.exists():
                    logger.warning(
                        "Ảnh không tồn tại, bỏ qua: %s", full_image_path
                    )
                    continue

                self.samples.append((full_image_path, label))

        logger.info(
            "FineTuneDataset: tải %d mẫu từ %s.", len(self.samples), csv_file
        )

    def __len__(self) -> int:
        """Trả về số lượng mẫu trong dataset."""
        return len(self.samples)

    def __getitem__(self, idx: int) -> Tuple:
        """
        Lấy một mẫu theo index.

        Args:
            idx: Index của mẫu cần lấy.

        Returns:
            Tuple (PIL Image, label_str) hoặc (transformed_image, label_str).
        """
        from PIL import Image  # Import lazy để tránh lỗi nếu chưa cài

        image_path, label = self.samples[idx]
        try:
            image = Image.open(image_path).convert("RGB")
        except Exception as e:
            logger.error("Lỗi mở ảnh %s: %s", image_path, e)
            # Trả về ảnh trắng 1x1 thay vì raise exception
            image = Image.new("RGB", (32, 32), color=(255, 255, 255))

        if self.transform:
            image = self.transform(image)

        return image, label

    def get_labels(self) -> List[str]:
        """Trả về danh sách tất cả nhãn trong dataset."""
        return [label for _, label in self.samples]


# ============================================================
# Config & Setup
# ============================================================

def prepare_config(
    base_model: str,
    data_dir: str,
    save_dir: str,
    batch_size: int = 32,
    lr: float = 1e-4,
):
    """
    Tạo VietOCR config cho fine-tune.

    Args:
        base_model: Tên mô hình gốc VietOCR ('vgg_transformer', 'vgg_seq2seq').
        data_dir: Thư mục chứa dữ liệu huấn luyện.
        save_dir: Thư mục lưu checkpoint mô hình.
        batch_size: Số lượng mẫu mỗi batch.
        lr: Learning rate ban đầu.

    Returns:
        Cfg object đã được cấu hình cho fine-tune.

    Raises:
        ImportError: Nếu vietocr chưa được cài đặt.
    """
    try:
        from vietocr.tool.config import Cfg
    except ImportError as e:
        raise ImportError("Thiếu thư viện vietocr. Chạy: pip install vietocr") from e

    # Tải config từ mô hình gốc
    config = Cfg.load_config_from_name(base_model)

    # Cấu hình đường dẫn dữ liệu
    # TODO: Thêm dữ liệu thật rồi chạy script này
    config["trainer"]["data_root"] = data_dir
    config["trainer"]["train_annotation"] = os.path.join(data_dir, "train.csv")
    config["trainer"]["valid_annotation"] = os.path.join(data_dir, "val.csv")

    # Cấu hình lưu checkpoint
    Path(save_dir).mkdir(parents=True, exist_ok=True)
    config["trainer"]["checkpoint"] = os.path.join(save_dir, "checkpoint.pth")
    config["trainer"]["export"] = os.path.join(save_dir, "best_model.pth")

    # Cấu hình siêu tham số
    config["trainer"]["batch_size"] = batch_size
    config["optimizer"]["lr"] = lr

    # Chọn thiết bị tự động
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    config["device"] = device
    logger.info("prepare_config(): device=%s, base_model=%s", device, base_model)

    return config


# ============================================================
# Training
# ============================================================

def run_finetune(config, epochs: int = 10) -> None:
    """
    Thực hiện vòng lặp fine-tune VietOCR.

    Args:
        config: VietOCR Cfg object đã được cấu hình (từ prepare_config).
        epochs: Số epoch huấn luyện. Mặc định 10.

    Note:
        - Checkpoint tốt nhất (theo validation loss) sẽ được lưu tự động.
        - Quá trình train sẽ log loss sau mỗi epoch.

    TODO: Thêm dữ liệu thật rồi chạy script này
    """
    try:
        from vietocr.tool.trainer import Trainer
    except ImportError as e:
        raise ImportError("Thiếu vietocr.tool.trainer") from e

    # Ghi đè số epoch vào config
    config["trainer"]["epochs"] = epochs

    logger.info("Bắt đầu fine-tune: %d epochs.", epochs)
    logger.info("Train annotation: %s", config["trainer"]["train_annotation"])
    logger.info("Valid annotation: %s", config["trainer"]["valid_annotation"])
    logger.info("Checkpoint sẽ lưu tại: %s", config["trainer"]["checkpoint"])

    try:
        trainer = Trainer(config, pretrained=True)
        trainer.train()
        logger.info("Fine-tune hoàn tất. Best model: %s", config["trainer"]["export"])
    except FileNotFoundError as e:
        logger.error(
            "Không tìm thấy file dữ liệu. Hãy tạo train.csv và val.csv trước: %s", e
        )
        raise
    except Exception as e:
        logger.error("Lỗi trong quá trình fine-tune: %s", e)
        raise


# ============================================================
# Evaluation
# ============================================================

def evaluate(config, test_dir: str) -> dict:
    """
    Đánh giá mô hình đã fine-tune trên tập test.

    Tính các chỉ số:
    - CER (Character Error Rate): tỉ lệ ký tự nhận dạng sai.
    - WER (Word Error Rate): tỉ lệ từ nhận dạng sai.

    Args:
        config: VietOCR Cfg object (đã trỏ đến best_model.pth).
        test_dir: Thư mục chứa test.csv và ảnh test.

    Returns:
        Dict gồm:
            - 'cer': Character Error Rate (float, thấp hơn là tốt hơn)
            - 'wer': Word Error Rate (float, thấp hơn là tốt hơn)
            - 'accuracy': Tỉ lệ chính xác hoàn toàn (exact match)
            - 'total': Tổng số mẫu test

    TODO: Thêm dữ liệu thật rồi chạy script này
    """
    try:
        from vietocr.tool.predictor import Predictor
        from PIL import Image
    except ImportError as e:
        raise ImportError("Thiếu thư viện vietocr hoặc pillow") from e

    test_csv = os.path.join(test_dir, "test.csv")
    if not os.path.exists(test_csv):
        raise FileNotFoundError(f"Không tìm thấy test.csv tại: {test_csv}")

    # Tải mô hình đã fine-tune
    best_model_path = config["trainer"]["export"]
    if os.path.exists(best_model_path):
        config["weights"] = best_model_path
        logger.info("evaluate(): tải best model từ %s.", best_model_path)
    else:
        logger.warning("Không tìm thấy best model tại %s, dùng pretrained.", best_model_path)

    predictor = Predictor(config)

    # Đọc dữ liệu test
    test_dataset = FineTuneDataset(csv_file=test_csv, data_dir=test_dir)
    total = len(test_dataset)
    if total == 0:
        logger.warning("evaluate(): dataset test rỗng.")
        return {"cer": 0.0, "wer": 0.0, "accuracy": 0.0, "total": 0}

    logger.info("evaluate(): đánh giá trên %d mẫu...", total)

    total_cer = 0.0
    total_wer = 0.0
    exact_match = 0

    for idx in range(total):
        pil_img, ground_truth = test_dataset[idx]
        try:
            pred_result = predictor.predict(pil_img, return_prob=True)
            if isinstance(pred_result, tuple):
                predicted_text = pred_result[0]
            else:
                predicted_text = str(pred_result)
        except Exception as e:
            logger.warning("Lỗi predict mẫu %d: %s", idx, e)
            predicted_text = ""

        # Tính CER (Levenshtein distance / len(ground_truth))
        cer = _compute_cer(predicted_text, ground_truth)
        wer = _compute_wer(predicted_text, ground_truth)
        total_cer += cer
        total_wer += wer

        if predicted_text.strip() == ground_truth.strip():
            exact_match += 1

    avg_cer = total_cer / total
    avg_wer = total_wer / total
    accuracy = exact_match / total

    metrics = {
        "cer": round(avg_cer, 4),
        "wer": round(avg_wer, 4),
        "accuracy": round(accuracy, 4),
        "total": total,
    }

    logger.info(
        "Kết quả đánh giá | CER: %.4f | WER: %.4f | Accuracy: %.4f | Tổng: %d",
        avg_cer, avg_wer, accuracy, total,
    )
    return metrics


# ============================================================
# Metric Helpers
# ============================================================

def _compute_cer(predicted: str, reference: str) -> float:
    """
    Tính Character Error Rate (CER) giữa predicted và reference.

    CER = edit_distance(predicted, reference) / len(reference)

    Args:
        predicted: Chuỗi được nhận dạng.
        reference: Chuỗi ground truth.

    Returns:
        CER trong khoảng [0.0, ...]. 0.0 là hoàn hảo.
    """
    if len(reference) == 0:
        return 0.0 if len(predicted) == 0 else 1.0

    distance = _levenshtein(predicted, reference)
    return distance / len(reference)


def _compute_wer(predicted: str, reference: str) -> float:
    """
    Tính Word Error Rate (WER) giữa predicted và reference.

    WER = edit_distance(words_pred, words_ref) / len(words_ref)

    Args:
        predicted: Chuỗi được nhận dạng.
        reference: Chuỗi ground truth.

    Returns:
        WER trong khoảng [0.0, ...]. 0.0 là hoàn hảo.
    """
    ref_words = reference.split()
    pred_words = predicted.split()

    if len(ref_words) == 0:
        return 0.0 if len(pred_words) == 0 else 1.0

    distance = _levenshtein(pred_words, ref_words)
    return distance / len(ref_words)


def _levenshtein(s1, s2) -> int:
    """
    Tính khoảng cách Levenshtein giữa hai chuỗi (hoặc list).

    Args:
        s1: Chuỗi hoặc list nguồn.
        s2: Chuỗi hoặc list đích.

    Returns:
        Số thao tác chỉnh sửa tối thiểu (insert, delete, replace).
    """
    m, n = len(s1), len(s2)
    # Ma trận DP kích thước (m+1) x (n+1)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,        # xóa
                dp[i][j - 1] + 1,        # chèn
                dp[i - 1][j - 1] + cost, # thay thế
            )

    return dp[m][n]


# ============================================================
# Entry Point
# ============================================================

def _parse_args() -> argparse.Namespace:
    """
    Phân tích tham số dòng lệnh.

    Returns:
        Namespace chứa các tham số: data_dir, save_dir, base_model, epochs.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Fine-tune VietOCR trên dữ liệu sổ đỏ/sổ hồng.\n\n"
            "TODO: Thêm dữ liệu thật (train.csv, val.csv, test.csv + ảnh) rồi chạy script này."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--data-dir",
        type=str,
        required=True,
        help="Thư mục chứa train.csv, val.csv, test.csv và thư mục images/.",
    )
    parser.add_argument(
        "--save-dir",
        type=str,
        required=True,
        help="Thư mục lưu checkpoint và best model.",
    )
    parser.add_argument(
        "--base-model",
        type=str,
        default="vgg_transformer",
        choices=["vgg_transformer", "vgg_seq2seq"],
        help="Mô hình VietOCR gốc để fine-tune. Mặc định: vgg_transformer.",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=10,
        help="Số epoch huấn luyện. Mặc định: 10.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size. Mặc định: 32.",
    )
    parser.add_argument(
        "--lr",
        type=float,
        default=1e-4,
        help="Learning rate. Mặc định: 1e-4.",
    )
    parser.add_argument(
        "--eval-only",
        action="store_true",
        help="Chỉ chạy evaluate (bỏ qua training). Cần best_model.pth tồn tại.",
    )

    return parser.parse_args()


def main() -> None:
    """
    Hàm main: fine-tune và/hoặc đánh giá mô hình VietOCR.

    # TODO: Thêm dữ liệu thật rồi chạy script này
    """
    args = _parse_args()

    logger.info("=" * 60)
    logger.info("VietOCR Fine-tune Scaffold - Sổ đỏ / Sổ hồng OCR")
    logger.info("=" * 60)
    logger.info("data_dir   : %s", args.data_dir)
    logger.info("save_dir   : %s", args.save_dir)
    logger.info("base_model : %s", args.base_model)
    logger.info("epochs     : %d", args.epochs)
    logger.info("batch_size : %d", args.batch_size)
    logger.info("lr         : %g", args.lr)
    logger.info("eval_only  : %s", args.eval_only)
    logger.info("=" * 60)

    # Tạo config
    config = prepare_config(
        base_model=args.base_model,
        data_dir=args.data_dir,
        save_dir=args.save_dir,
        batch_size=args.batch_size,
        lr=args.lr,
    )

    if not args.eval_only:
        # ---- BƯỚC 1: Fine-tune ----
        # TODO: Thêm dữ liệu thật rồi chạy script này
        logger.info("Bắt đầu bước fine-tune...")
        run_finetune(config, epochs=args.epochs)
    else:
        logger.info("Bỏ qua bước fine-tune (--eval-only).")

    # ---- BƯỚC 2: Evaluate ----
    logger.info("Bắt đầu bước evaluate...")
    try:
        metrics = evaluate(config, test_dir=args.data_dir)
        logger.info("---- KẾT QUẢ ĐÁNH GIÁ ----")
        logger.info("  CER      : %.4f (%.2f%%)", metrics["cer"], metrics["cer"] * 100)
        logger.info("  WER      : %.4f (%.2f%%)", metrics["wer"], metrics["wer"] * 100)
        logger.info("  Accuracy : %.4f (%.2f%%)", metrics["accuracy"], metrics["accuracy"] * 100)
        logger.info("  Tổng mẫu : %d", metrics["total"])
    except FileNotFoundError:
        logger.warning(
            "Không tìm thấy test.csv. Bỏ qua bước evaluate. "
            "Tạo file test.csv trong data_dir để kích hoạt evaluate."
        )


if __name__ == "__main__":
    # ============================================================
    # TODO: Thêm dữ liệu thật rồi chạy script này
    # Ví dụ chạy:
    #   python fine_tune_scaffold.py \
    #       --data-dir ./data/sodo \
    #       --save-dir ./checkpoints/sodo \
    #       --base-model vgg_transformer \
    #       --epochs 20
    # ============================================================
    main()
