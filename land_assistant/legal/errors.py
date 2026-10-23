"""Safe machine diagnostics: never include provider payloads or user text."""
class LegalError(ValueError):
    def __init__(self,code,*,http_status=None):
        self.code=code
        self.http_status=http_status
        super().__init__(code)
