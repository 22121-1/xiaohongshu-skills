"""注册当前安装的业务模块；新增模块必须提供 register 函数。"""

from importlib import import_module
from pkgutil import iter_modules


def register_all(subparsers, connect, output):
    for info in sorted(iter_modules(__path__), key=lambda item: item.name):
        if info.ispkg or info.name.startswith("_"):
            continue
        module = import_module(f"{__name__}.{info.name}")
        module.register(subparsers, connect, output)
