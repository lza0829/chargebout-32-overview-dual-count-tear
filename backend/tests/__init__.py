"""测试包：进程级独立临时库（须先于 app.* 导入设定）。"""
import os
import tempfile

os.environ.setdefault(
    "CHARGEBOUT_DB",
    os.path.join(tempfile.mkdtemp(prefix="chargebout-tests-"), "boot.db"),
)
