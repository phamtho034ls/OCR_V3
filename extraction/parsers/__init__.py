"""
extraction/parsers/__init__.py - Modular Domain Parsers for GCN entities.
"""

from .owner_parser import OwnerParser
from .parcel_parser import ParcelParser
from .area_parser import AreaParser
from .certification_parser import CertificationParser
from .transfer_parser import TransferParser

__all__ = [
    "OwnerParser",
    "ParcelParser",
    "AreaParser",
    "CertificationParser",
    "TransferParser",
]
