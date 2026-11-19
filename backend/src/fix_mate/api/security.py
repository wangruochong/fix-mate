"""本地访问保护。

服务只监听 127.0.0.1,但本机上的任何网页都能向它发请求(跨站请求伪造),
也可能通过 DNS 重绑定把别的域名指到本机。FixMate 能 push 代码、触发打包,不能被网页随便调用,所以:

- Host 头必须是本机地址(挡住 DNS 重绑定);
- 如果请求带 Origin 头(浏览器跨站请求一定会带),它也必须是本机地址(挡住别的网站)。

命令行工具(curl)没有 Origin 头,不受影响。端口不限制,因为开发时前端和后端端口不同。
"""

import json
from urllib.parse import urlparse

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _hostname(host_header: str) -> str:
    """去掉端口,兼容 [::1]:8000 这种写法。"""
    if host_header.startswith("["):
        return host_header[1 : host_header.index("]")]
    return host_header.rsplit(":", 1)[0] if host_header.count(":") == 1 else host_header


class LocalOnlyMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and not self._allowed(scope):
            body = json.dumps({"message": "只允许从本机访问"}, ensure_ascii=False).encode()
            await send(
                {"type": "http.response.start", "status": 403, "headers": [(b"content-type", b"application/json")]}
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)

    @staticmethod
    def _allowed(scope) -> bool:
        headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        if _hostname(headers.get("host", "")) not in LOCAL_HOSTS:
            return False
        origin = headers.get("origin")
        return origin is None or (urlparse(origin).hostname or "") in LOCAL_HOSTS
