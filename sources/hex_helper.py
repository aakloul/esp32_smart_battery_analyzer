"""hex_helper.py

Utility class that groups together the small helper functions that deal with
hex formatting and HMAC verification.

Typical usage
-------------
>>> from hex_helper import HexHelper
>>> helper = HexHelper(secret_key="mySecret")
>>> helper.print_hex(b"\x01\x02")
01:02
>>> ok = helper.verify_signature(tlm_payload, mac)
"""

import hmac
import hashlib
from typing import Union


class HexHelper:
    """
    Helper for hexadecimal conversion and HMAC‑SHA256 verification.

    Parameters
    ----------
    secret_key : str
        Secret used to compute the HMAC. It is encoded as UTF‑8 before use.
    """

    def __init__(self, secret_key: str):
        self.secret_key = secret_key.encode()      # bytes for HMAC

    # ------------------------------------------------------------------
    # Hex conversion helpers
    # ------------------------------------------------------------------
    @staticmethod
    def to_hex_string(byte_array: Union[bytes, bytearray]) -> str:
        """
        Convert a sequence of bytes to a colon‑separated hex string.

        Example
        -------
        >>> HexHelper.to_hex_string(b"\x01\xab")
        '01:ab'
        """
        return ":".join(f"{c:02x}" for c in byte_array)

    @classmethod
    def print_hex(cls, byte_array: Union[bytes, bytearray]) -> None:
        """Pretty‑print a byte sequence using : as separator."""
        print(cls.to_hex_string(byte_array))

    # ------------------------------------------------------------------
    # HMAC verification
    # ------------------------------------------------------------------
    def verify_signature(self, tlm: bytes, mac: bytes, trunc_len: int = 4) -> bool:
        """
        Re‑compute HMAC‑SHA256 over the raw TLM payload and compare the
        truncated MAC (first *trunc_len* bytes).

        Parameters
        ----------
        tlm : bytes
            The raw TLM payload (without the trailing MAC).
        mac : bytes
            The MAC extracted from the advertisement.
        trunc_len : int, optional
            Number of leading bytes of the full HMAC that are transmitted.
            The original script used 4, which is kept as the default.

        Returns
        -------
        bool
            ``True`` if the computed truncated MAC matches the supplied one.
        """
        full_hmac = hmac.new(self.secret_key, tlm, hashlib.sha256).digest()
        return full_hmac[:trunc_len] == mac
