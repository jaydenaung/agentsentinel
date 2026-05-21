"""Static analysis engine — extracts tool definitions from Python agent files using AST."""

import ast
import dataclasses
from pathlib import Path


@dataclasses.dataclass
class ToolInfo:
    name: str
    scope: str          # "read" | "write"
    is_dangerous: bool
    source: str         # how it was detected
    docstring: str = ""


@dataclasses.dataclass
class AgentInfo:
    file: Path
    tools: list[ToolInfo]
    description: str = ""
    model: str = ""


_WRITE_PATTERNS = (
    "write", "edit", "create", "delete", "remove", "move", "rename",
    "execute", "run", "exec", "patch", "update", "insert", "drop",
    "truncate", "send", "post", "put", "upload", "deploy", "reset", "kill",
)
_DANGEROUS_PATTERNS = (
    "delete", "remove", "drop", "truncate", "execute", "run", "exec",
    "send", "deploy", "reset", "kill",
)
_KNOWN_MODELS = (
    "gpt-", "claude-", "gemini-", "mistral", "llama", "mixtral",
    "command", "titan", "nova",
)


def _classify(name: str) -> tuple[str, bool]:
    lower = name.lower()
    is_dangerous = any(p in lower for p in _DANGEROUS_PATTERNS)
    is_write = is_dangerous or any(p in lower for p in _WRITE_PATTERNS)
    return ("write" if is_write else "read"), is_dangerous


def _get_string(node: ast.expr | None) -> str:
    """Extract a string constant from an AST node."""
    if node is None:
        return ""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ""


def _has_decorator(func_node: ast.FunctionDef | ast.AsyncFunctionDef, names: tuple[str, ...]) -> bool:
    for dec in func_node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id in names:
            return True
        if isinstance(dec, ast.Attribute) and dec.attr in names:
            return True
        # @tool(return_direct=True) style
        if isinstance(dec, ast.Call):
            if isinstance(dec.func, ast.Name) and dec.func.id in names:
                return True
            if isinstance(dec.func, ast.Attribute) and dec.func.attr in names:
                return True
    return False


class _AgentFileVisitor(ast.NodeVisitor):
    """Walk an AST and collect tool definitions and agent metadata."""

    def __init__(self) -> None:
        self.tools: list[ToolInfo] = []
        self.description: str = ""
        self.model: str = ""
        self._seen: set[str] = set()

    def _add_tool(self, name: str, source: str, docstring: str = "") -> None:
        if name in self._seen:
            return
        self._seen.add(name)
        scope, is_dangerous = _classify(name)
        self.tools.append(ToolInfo(
            name=name, scope=scope,
            is_dangerous=is_dangerous,
            source=source, docstring=docstring,
        ))

    # ------------------------------------------------------------------
    # @tool decorated functions
    # ------------------------------------------------------------------

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Covers @tool, @SentinelTool, @beta_tool, @betaZodTool, etc.
        if _has_decorator(node, ("tool", "SentinelTool", "beta_tool", "betaZodTool")):
            doc = ast.get_docstring(node) or ""
            self._add_tool(node.name, "@tool decorator", doc)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    # ------------------------------------------------------------------
    # Class-based tools: class MyTool(BaseTool): name = "my_tool"
    # ------------------------------------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        base_names = {
            b.id if isinstance(b, ast.Name) else
            (b.attr if isinstance(b, ast.Attribute) else "")
            for b in node.bases
        }
        if "BaseTool" in base_names or "StructuredTool" in base_names:
            for item in node.body:
                if (
                    isinstance(item, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "name" for t in item.targets)
                ):
                    tool_name = _get_string(item.value)
                    if tool_name:
                        doc = ast.get_docstring(node) or ""
                        self._add_tool(tool_name, "BaseTool subclass", doc)
        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Call-based tools: Tool(name="x"), StructuredTool.from_function(f, name="x")
    # ------------------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        if func_name in ("Tool", "StructuredTool"):
            for kw in node.keywords:
                if kw.arg == "name":
                    tool_name = _get_string(kw.value)
                    if tool_name:
                        self._add_tool(tool_name, f"{func_name}(name=...)")

        # Detect model strings: ChatAnthropic(model="claude-..."), ChatOpenAI(model="gpt-...")
        if func_name in ("ChatAnthropic", "ChatOpenAI", "ChatGoogleGenerativeAI",
                         "AzureChatOpenAI", "BedrockChat", "init_chat_model"):
            for kw in node.keywords:
                if kw.arg == "model":
                    val = _get_string(kw.value)
                    if val and not self.model:
                        self.model = val
            # positional: create_agent("openai:gpt-4o", ...)
            if node.args:
                val = _get_string(node.args[0])
                if val and any(val.startswith(p) for p in _KNOWN_MODELS) and not self.model:
                    self.model = val

        # create_agent("openai:gpt-4o", ...) — first arg is model string
        if func_name == "create_agent" and node.args:
            val = _get_string(node.args[0])
            if val and not self.model:
                self.model = val

        # SentinelCallbackHandler(description="...") — pick up agent description
        if func_name == "SentinelCallbackHandler":
            for kw in node.keywords:
                if kw.arg == "description" and not self.description:
                    self.description = _get_string(kw.value)

        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Module-level description strings assigned to variables
    # ------------------------------------------------------------------

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name) and "description" in target.id.lower():
                val = _get_string(node.value)
                if val and not self.description:
                    self.description = val
        self.generic_visit(node)


def scan_file(path: Path) -> AgentInfo | None:
    """Parse a Python file and extract agent/tool information. Returns None on parse error."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, OSError):
        return None

    visitor = _AgentFileVisitor()
    visitor.visit(tree)

    if not visitor.tools:
        return None

    return AgentInfo(
        file=path,
        tools=visitor.tools,
        description=visitor.description,
        model=visitor.model,
    )


def scan_path(target: Path) -> list[AgentInfo]:
    """Scan a file or directory, returning one AgentInfo per file that contains tools."""
    if target.is_file():
        result = scan_file(target)
        return [result] if result else []

    results = []
    for py_file in sorted(target.rglob("*.py")):
        # Skip obvious non-agent files
        if any(part.startswith((".venv", "venv", "__pycache__", ".git", "node_modules"))
               for part in py_file.parts):
            continue
        result = scan_file(py_file)
        if result:
            results.append(result)
    return results
