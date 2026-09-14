"""
Mô-đun nhận dạng văn bản sử dụng VietOCR.

Module này cung cấp class VietOCRRecognizer để nhận dạng văn bản tiếng Việt
từ các vùng ảnh đã được phát hiện, hỗ trợ cả single-image và batch inference.
"""

import logging
from typing import List, Tuple, Dict, Optional

try:
    import torch
except Exception:
    pass

try:
    from ocr_so_do.infrastructure.memory import cleanup_memory
except Exception:
    cleanup_memory = None

import numpy as np
from PIL import Image

# Thiết lập logger cho module này
logger = logging.getLogger(__name__)

# Nguồn kết quả trả về
SOURCE_VIETOCR = "vietocr"
SOURCE_PADDLEOCR = "paddleocr"


class VietOCRRecognizer:
    """
    Nhận dạng văn bản tiếng Việt sử dụng VietOCR.

    Hỗ trợ nhận dạng đơn lẻ và batch, có cơ chế fallback sang kết quả
    PaddleOCR khi độ tin cậy của VietOCR thấp hơn ngưỡng cho phép.

    Attributes:
        _predictor: Instance của VietOCR Predictor.
        _model_name: Tên mô hình đang sử dụng.
        _device: Thiết bị inference ('cuda:0', 'cpu', ...).

    Example:
        >>> recognizer = VietOCRRecognizer(model_name='vgg_transformer', device='cuda:0')
        >>> text, conf = recognizer.recognize(crop_image)
        >>> print(f"Text: {text}, Confidence: {conf:.2f}")
    """

    def __init__(
        self,
        model_name: str = "vgg_transformer",
        device: str = "cuda:0",
    ) -> None:
        """
        Khởi tạo VietOCRRecognizer.

        Args:
            model_name: Tên mô hình VietOCR. Các lựa chọn phổ biến:
                - 'vgg_transformer' (mặc định, chính xác cao)
                - 'vgg_seq2seq' (nhẹ hơn)
            device: Thiết bị inference PyTorch. Mặc định 'cuda:0'.
                Tự động fallback về 'cpu' nếu CUDA không khả dụng.

        Raises:
            ImportError: Nếu thư viện vietocr chưa được cài đặt.
            RuntimeError: Nếu không thể khởi tạo mô hình dù đã fallback CPU.
        """
        try:
            from vietocr.tool.predictor import Predictor
            from vietocr.tool.config import Cfg
        except ImportError as e:
            logger.error("Lỗi khi import vietocr hoặc thư viện phụ thuộc: %s", e)
            raise ImportError(f"Lỗi nạp thư viện vietocr: {e}") from e

        self._model_name = model_name
        self._device = device

        # Thử khởi tạo với thiết bị được yêu cầu, fallback CPU nếu CUDA lỗi
        actual_device = self._resolve_device(device)
        self._predictor = self._init_predictor(Predictor, Cfg, model_name, actual_device)
        self._device = actual_device

        logger.info(
            "Đã khởi tạo VietOCR model '%s' trên %s.",
            model_name,
            actual_device,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recognize(self, image: np.ndarray) -> Tuple[str, float]:
        """
        Nhận dạng văn bản từ một ảnh crop.

        Args:
            image: Ảnh crop ở định dạng BGR (numpy array HxWxC) hoặc grayscale.
                   Thường là vùng ảnh chứa một dòng văn bản.

        Returns:
            Tuple (text, confidence):
                - text: Chuỗi văn bản được nhận dạng.
                - confidence: Độ tin cậy trong khoảng [0.0, 1.0].

            Trả về ('', 0.0) nếu ảnh không hợp lệ hoặc có lỗi.
        """
        if image is None or image.size == 0:
            logger.warning("recognize() nhận ảnh rỗng hoặc None.")
            return ("", 0.0)

        try:
            import torch
            pil_img = self._bgr_to_pil(image)
            with torch.no_grad():
                result = self._predictor.predict(pil_img, return_prob=True)
            del pil_img

            # VietOCR predict trả về (text, prob) hoặc chỉ text tuỳ phiên bản
            if isinstance(result, tuple) and len(result) == 2:
                text, confidence = result[0], float(result[1])
            else:
                text, confidence = str(result), 0.0

            logger.debug("recognize(): '%s' (conf=%.3f)", text, confidence)
            return (text, confidence)

        except Exception as e:
            logger.error("Lỗi khi nhận dạng ảnh: %s", e)
            return ("", 0.0)

    def recognize_batch(
        self,
        images: List[np.ndarray],
    ) -> List[Tuple[str, float]]:
        """
        Nhận dạng văn bản theo batch để tăng throughput.

        Args:
            images: Danh sách ảnh crop ở định dạng BGR numpy array.

        Returns:
            List các tuple (text, confidence) tương ứng với từng ảnh.
            Các ảnh lỗi sẽ trả về ('', 0.0) tại vị trí tương ứng.
        """
        if not images:
            logger.warning("recognize_batch() nhận list ảnh rỗng.")
            return []

        # Lọc và convert ảnh hợp lệ, giữ index để map kết quả
        pil_images: List[Optional[Image.Image]] = []
        for idx, img in enumerate(images):
            if img is None or img.size == 0:
                logger.warning("Ảnh tại index %d không hợp lệ, bỏ qua.", idx)
                pil_images.append(None)
            else:
                pil_images.append(self._bgr_to_pil(img))

        results: List[Tuple[str, float]] = []

        try:
            import torch
            # Tách ảnh hợp lệ để chạy batch
            valid_imgs = [img for img in pil_images if img is not None]
            valid_pairs: List[Tuple[str, float]] = []

            if valid_imgs:
                # Phân đoạn batch (chunking) tối đa 16 ảnh để tránh cấp phát tensor khổng lồ gây OOM VRAM
                chunk_size = 16
                for c_idx in range(0, len(valid_imgs), chunk_size):
                    chunk_imgs = valid_imgs[c_idx : c_idx + chunk_size]
                    with torch.no_grad():
                        batch_preds = self._predictor.predict_batch(
                            chunk_imgs, return_prob=True
                        )
                    # VietOCR predict_batch(return_prob=True) trả về (list_texts, list_probs)
                    if isinstance(batch_preds, tuple) and len(batch_preds) == 2:
                        valid_pairs.extend(
                            zip(batch_preds[0], [float(p) for p in batch_preds[1]])
                        )
                    elif isinstance(batch_preds, list):
                        valid_pairs.extend([(str(p), 0.90) for p in batch_preds])
                    else:
                        valid_pairs.append((str(batch_preds), 0.90))

                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()

            # Map kết quả trở lại theo thứ tự gốc
            pair_iter = iter(valid_pairs)
            for pil_img in pil_images:
                if pil_img is None:
                    results.append(("", 0.0))
                else:
                    try:
                        t, c = next(pair_iter)
                        results.append((str(t), float(c)))
                    except StopIteration:
                        results.append(("", 0.0))

        except Exception as e:
            logger.error("Lỗi khi nhận dạng batch: %s. Fallback sang từng ảnh.", e)
            # Fallback: nhận dạng từng ảnh riêng lẻ
            results = []
            for img in images:
                results.append(self.recognize(img))
        finally:
            del pil_images
            try:
                del valid_imgs
            except Exception:
                pass
            if cleanup_memory:
                cleanup_memory(force_os_trim=False)
            else:
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                except Exception:
                    pass
                import gc
                gc.collect()

        logger.debug("recognize_batch(): xử lý %d ảnh.", len(results))
        return results

    def recognize_with_fallback(
        self,
        image: np.ndarray,
        bbox: Dict,
        paddle_results: List[Dict],
        threshold: float = 0.5,
    ) -> Tuple[str, float, str]:
        """
        Nhận dạng văn bản với cơ chế fallback sang kết quả PaddleOCR.

        Ưu tiên kết quả VietOCR nếu độ tin cậy >= threshold.
        Ngược lại, tìm kết quả PaddleOCR khớp với bbox và dùng làm fallback.

        Args:
            image: Ảnh crop tương ứng với bbox cần nhận dạng.
            bbox: Dict chứa key ``bbox`` (list 4 điểm) của vùng cần nhận dạng.
            paddle_results: Kết quả từ PaddleOCRDetector.detect() — list các dict
                với keys ``bbox``, ``text``, ``confidence``.
            threshold: Ngưỡng độ tin cậy tối thiểu của VietOCR. Mặc định 0.5.

        Returns:
            Tuple (text, confidence, source):
                - text: Chuỗi văn bản.
                - confidence: Độ tin cậy.
                - source: 'vietocr' hoặc 'paddleocr' cho biết nguồn kết quả.
        """
        # Thử nhận dạng bằng VietOCR trước
        viet_text, viet_conf = self.recognize(image)

        if viet_conf >= threshold:
            logger.debug(
                "recognize_with_fallback(): dùng VietOCR '%s' (conf=%.3f >= threshold=%.2f).",
                viet_text, viet_conf, threshold,
            )
            return (viet_text, viet_conf, SOURCE_VIETOCR)

        # VietOCR không đủ tin cậy → tìm kết quả PaddleOCR tương ứng
        logger.debug(
            "recognize_with_fallback(): VietOCR conf=%.3f < threshold=%.2f, thử PaddleOCR.",
            viet_conf, threshold,
        )

        target_bbox = bbox.get("bbox")
        if target_bbox and paddle_results:
            best_match = self._find_best_paddle_match(target_bbox, paddle_results)
            if best_match:
                paddle_text = best_match.get("text", "")
                paddle_conf = float(best_match.get("confidence", 0.0))
                logger.debug(
                    "recognize_with_fallback(): fallback PaddleOCR '%s' (conf=%.3f).",
                    paddle_text, paddle_conf,
                )
                return (paddle_text, paddle_conf, SOURCE_PADDLEOCR)

        # Không tìm được kết quả PaddleOCR phù hợp, trả về VietOCR dù conf thấp
        logger.warning(
            "recognize_with_fallback(): không tìm được PaddleOCR match, dùng VietOCR conf thấp."
        )
        return (viet_text, viet_conf, SOURCE_VIETOCR)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_device(device: str) -> str:
        """
        Kiểm tra CUDA khả dụng, fallback sang CPU nếu cần.

        Args:
            device: Chuỗi thiết bị ('cuda:0', 'cpu', ...).

        Returns:
            Chuỗi thiết bị thực tế sẽ được sử dụng.
        """
        if "cuda" in device.lower():
            try:
                import torch
                if not torch.cuda.is_available():
                    logger.warning(
                        "CUDA không khả dụng trên máy này. Fallback sang CPU."
                    )
                    return "cpu"
            except ImportError:
                logger.warning("Không tìm thấy PyTorch. Fallback sang CPU.")
                return "cpu"
        return device

    @staticmethod
    def _init_predictor(Predictor, Cfg, model_name: str, device: str):
        """
        Tạo instance Predictor của VietOCR.

        Args:
            Predictor: Class Predictor từ vietocr.
            Cfg: Class Cfg từ vietocr.
            model_name: Tên mô hình VietOCR.
            device: Thiết bị inference.

        Returns:
            Instance Predictor đã khởi tạo.

        Raises:
            RuntimeError: Nếu không thể khởi tạo Predictor.
        """
        try:
            import json
            from pathlib import Path

            candidate_cfg_paths = [
                Path(__file__).resolve().parents[2] / "configs" / f"{model_name}_config.json",
                Path(__file__).resolve().parents[3] / "configs" / f"{model_name}_config.json",
                Path(__file__).parent.parent / "configs" / f"{model_name}_config.json",
            ]
            local_cfg_path = next((p for p in candidate_cfg_paths if p.exists()), candidate_cfg_paths[0])
            if local_cfg_path.exists():
                with open(local_cfg_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            else:
                try:
                    config = Cfg.load_config_from_name(model_name)
                except Exception:
                    import urllib3
                    urllib3.disable_warnings()
                    import requests
                    import yaml
                    r1 = requests.get('https://vocr.vn/data/vietocr/config/base.yml', verify=False)
                    r2 = requests.get(f'https://vocr.vn/data/vietocr/config/{model_name.replace("_", "-")}.yml', verify=False)
                    config = yaml.safe_load(r1.text)
                    config.update(yaml.safe_load(r2.text))

            config["device"] = device
            if "cnn" in config and isinstance(config["cnn"], dict):
                config["cnn"]["pretrained"] = False

            # Ưu tiên load weights trực tiếp từ thư mục backend/weights hoặc root weights
            candidate_weight_paths = [
                Path(__file__).resolve().parents[2] / "weights" / f"{model_name}.pth",
                Path(__file__).resolve().parents[3] / "weights" / f"{model_name}.pth",
                Path(__file__).parent.parent / "weights" / f"{model_name}.pth",
            ]
            weights_path = next((p for p in candidate_weight_paths if p.exists()), candidate_weight_paths[0])
            if weights_path.exists():
                config["weights"] = str(weights_path)

            predictor = Predictor(config)
            return predictor
        except Exception as e:
            logger.error("Không thể khởi tạo VietOCR Predictor: %s", e)
            raise RuntimeError(f"Khởi tạo VietOCR Predictor thất bại: {e}") from e

    @staticmethod
    def _bgr_to_pil(image: np.ndarray) -> Image.Image:
        """
        Chuyển đổi ảnh BGR numpy array sang PIL Image RGB.

        Args:
            image: Ảnh BGR hoặc grayscale (numpy array).

        Returns:
            PIL Image ở định dạng RGB.
        """
        if len(image.shape) == 2:
            # Ảnh grayscale → convert sang RGB
            return Image.fromarray(image).convert("RGB")
        # BGR → RGB
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)

    @staticmethod
    def _find_best_paddle_match(
        target_bbox: List,
        paddle_results: List[Dict],
        iou_threshold: float = 0.3,
    ) -> Optional[Dict]:
        """
        Tìm kết quả PaddleOCR có bbox gần nhất với target_bbox.

        Sử dụng khoảng cách trung tâm đơn giản để khớp bbox.

        Args:
            target_bbox: List 4 điểm của bbox cần tìm.
            paddle_results: Danh sách kết quả PaddleOCR.
            iou_threshold: Ngưỡng IoU tối thiểu (chưa dùng, dự phòng).

        Returns:
            Dict kết quả PaddleOCR khớp nhất, hoặc None nếu không tìm thấy.
        """
        if not target_bbox or not paddle_results:
            return None

        def _center(bbox):
            """Tính tâm của bbox (list 4 điểm)."""
            xs = [pt[0] for pt in bbox]
            ys = [pt[1] for pt in bbox]
            return (sum(xs) / 4, sum(ys) / 4)

        target_cx, target_cy = _center(target_bbox)
        best_item = None
        best_dist = float("inf")

        for item in paddle_results:
            paddle_bbox = item.get("bbox")
            if not paddle_bbox:
                continue
            cx, cy = _center(paddle_bbox)
            dist = ((cx - target_cx) ** 2 + (cy - target_cy) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_item = item

        return best_item

    def __repr__(self) -> str:
        return (
            f"VietOCRRecognizer(model_name={self._model_name!r}, "
            f"device={self._device!r})"
        )


# Import cv2 ở đây để tránh circular import khi _bgr_to_pil dùng cv2
try:
    import cv2
except ImportError:
    # Fallback nếu opencv chưa cài
    cv2 = None  # type: ignore
