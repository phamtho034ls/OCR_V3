"""
extraction/validators.py - Proxy / Alias Layer for Domain Validators.

Single Source of Truth: ocr_so_do.domain.rules.validation.validators
All validation and normalization rules must be modified in the domain package.
This file re-exports everything to ensure 100% backward compatibility
while completely eliminating 1,100+ lines of duplicate code.
"""

from ocr_so_do.domain.rules.validation.validators import (
    GCNValidators,
    truncate_address_after_province,
    truncate_serial_noise,
    VALID_LAND_CODES,
    LAND_PURPOSE_RULES,
    AGENCY_KEYWORDS,
    SERIAL_TAIL_RE,
)

__all__ = [
    "GCNValidators",
    "truncate_address_after_province",
    "truncate_serial_noise",
    "VALID_LAND_CODES",
    "LAND_PURPOSE_RULES",
    "AGENCY_KEYWORDS",
    "SERIAL_TAIL_RE",
]
