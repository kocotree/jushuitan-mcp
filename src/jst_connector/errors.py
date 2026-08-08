class JstError(Exception):
    """连接器基础异常。"""


class JstConfigError(JstError):
    """本地配置缺失或无效。"""


class JstApiError(JstError):
    """聚水潭 OpenAPI 返回错误。"""

    def __init__(self, message: str, *, code: int | str | None = None):
        super().__init__(message)
        self.code = code
