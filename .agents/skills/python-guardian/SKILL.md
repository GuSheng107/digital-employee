---
name: python-guardian
description: 提供一套完整的 Python 代码规范，涵盖 PEP 8、类型注解、文档字符串、异常处理、现代 Python 实践以及 uv 项目管理。当 Agent 需要处理 Python 代码时，必须严格应用本技能的所有规则。
---

# 技能：Python 规范守卫者 (python-guardian)

## 代码规范细则

### 1. 格式与布局
- 缩进：4 个空格，严禁使用 Tab。
- 行宽：不超过 100 字符（文档字符串或注释可为 72 字符）。
- 空行：模块级函数与类定义之间空两行；类内方法定义之间空一行。
- 导入：每个导入独占一行，按 **标准库 → 第三方库 → 本地模块** 分组，组间空行；禁止使用 `from module import *`。
- 行尾：无多余空格；文件末尾有且仅有一个换行符。
- 字符串引号：统一使用双引号 `"`，除非字符串内包含双引号。

### 2. 命名约定
- 变量、函数、方法：`snake_case`
- 类、异常：`PascalCase`
- 常量：`UPPER_CASE_WITH_UNDERSCORES`
- 私有成员：单下划线 `_internal` 开头；内部私有可用双下划线 `__private`
- 布尔变量：使用 `is_`, `has_` 前缀（如 `is_valid`, `has_items`）
- 避免单字母变量，除非在推导式或极短作用域中（如 `for i in range(10)`）可接受。

### 3. 类型注解
- 必须使用现代语法：`list[int]` 代替 `List[int]`，`dict[str, float]`，`tuple[int, ...]`。
- 可选类型：`int | None` 而非 `Optional[int]`。
- 函数签名必须为每个参数添加类型，并注明返回类型。
- 复杂类型使用 `TypeAlias` 声明别名。
- 示例：
  ```python
  from typing import TypeAlias

  UserData: TypeAlias = dict[str, int | str]

  def process_user(data: UserData, /, *, timeout: float | None = None) -> bool:
      ...
  ```

### 4. 文档字符串 (Google 风格)
- 每个公共模块、类、方法/函数必须有 docstring，使用三重双引号。
- 结构：一行摘要（命令式语气），空行，详细描述，空行，Args/Returns/Raises/Yields 等节。
- 文档内容可用中文撰写，但节关键字（Args, Returns 等）保持英文。
- 示例：
  ```python
  def calculate_total(prices: list[float], tax_rate: float = 0.0) -> float:
      """计算含税总价。

      接受一个价格列表和可选税率，返回四舍五入到两位小数的总金额。

      Args:
          prices: 商品价格列表，每个元素须 >= 0。
          tax_rate: 税率，默认 0.0（表示 0%）。

      Returns:
          含税总金额，保留两位小数。

      Raises:
          ValueError: 若任何价格为负数。
      """
      ...
  ```

### 5. 函数与方法 design
- 单一职责：每个函数只做一件事，长度尽量不超过 50 行。
- 参数：尽量使用仅关键字参数 `*`；布尔参数鼓励使用关键字参数调用。
- 避免可变默认参数：用 `None` 替代并在函数体内初始化。
- 返回：保持返回类型一致，避免混合返回 `None` 和其他类型。
- 优先使用 `def` 而非 `lambda`，除非作为极简回调。

### 6. 类与面向对象
- 使用 `@dataclass` 或 `NamedTuple` 表示纯数据载体。
- 多重继承需谨慎并明确使用 `super()`。
- `__str__` 返回人类可读的描述，`__repr__` 返回可重建对象的表示。
- 使用 `@property` 定义只读/计算属性。

### 7. 错误处理与异常
- 捕获具体异常，决不可使用裸露的 `except:`，除非是记录后重新抛出或清理操作。
- 自定义异常继承自 `Exception`，并提供清晰的错误消息。
- 始终使用 `with` 语句管理文件、锁、网络连接等资源。
- 使用 `logging` 模块输出日志，不要用 `print()` 调试。

### 8. 现代 Python 最佳实践
- 使用 `pathlib.Path` 处理文件路径，而非 `os.path`。
- 字符串格式化优先使用 f-string。
- 序列拼接：使用 `''.join()` 而非循环中 `+`。
- 容器字面量：`[]`, `{}`, `()` 而非 `list()`, `dict()`, `tuple()`。
- 条件判断：利用真值判断，如 `if items:` 而非 `if len(items) > 0:`。
- 使用 `enumerate` 和 `zip` 简化循环，推导式保持简洁。

### 9. uv 版本与依赖管理
- 使用 `uv python install <version>` 安装指定 Python 版本。
- 使用 `uv python pin <version>` 固定项目版本（生成 `.python-version`）。
- 创建虚拟环境：`uv venv`。
- 添加依赖：`uv add <package>`（或 `uv pip install`），记录在 `pyproject.toml` 和 `uv.lock` 中。
- 新项目初始化：`uv init`。
- 运行脚本：`uv run <script>`。
- 必须提交 `uv.lock`，不要提交 `.venv` 目录。
- 开发工具（pytest, ruff, mypy）使用 `uv add --dev` 添加，并用 `uv run` 执行检查。

### 10. 测试与质量
- 使用 pytest，测试文件以 `test_` 开头。
- 测试函数命名：`test_<被测函数>_<场景>_<期望结果>`。
- 代码必须通过 `ruff` 或 `flake8` 零错误，并通过 `mypy --strict` 类型检查。

## 输出要求
应用本技能时，必须：
1. 输出符合所有上述规范 of Python 代码。
2. 若因特殊原因偏离规范，明确标注并给出理由。
3. 代码块后附上“规范检查清单”，确认类型注解、docstring、PEP8、异常处理、uv 项目结构等关键项均已满足。

## 禁止事项
- 绝不使用 `import *`、裸异常、无类型注解的公开函数、过时 Python 2 风格代码。
- 绝不忽略资源泄漏。
- 绝不使用 `eval()`、`exec()` 或不安全的 `pickle`。
- 绝不使用 `sed` 或 `awk` 处理含中文的文件。
- 绝不使用 `pip` 或 `python -m venv` 代替 `uv`，除非明确说明理由。
