"""业务错误。接口层会把它们转成 {message} 加对应的状态码,前端直接弹出这条中文提示。"""


class DomainError(Exception):
    """用户操作不被允许,或数据不存在。"""

    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(DomainError):
    status_code = 404
