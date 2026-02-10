from __future__ import annotations


class ASRError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class AudioConvertError(ASRError):
    def __init__(self, message: str = "Audio conversion failed.") -> None:
        super().__init__(code="ASR_FAILED", message=message)
