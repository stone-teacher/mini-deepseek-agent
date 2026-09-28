import ast
import math
import operator

from .models import Session, Todo, ToolSpec


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")

        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc

    def list_specs(self) -> list[ToolSpec]:
        return list(self._tools.values())

#计算__________________________________________________________________________________

_BINARY_OPERATORS = {
    ast.Add: operator.add, #加
    ast.Sub: operator.sub, #减
    ast.Mult: operator.mul, #乘
    ast.Div: operator.truediv, #除
    ast.FloorDiv: operator.floordiv, #整除
    ast.Mod: operator.mod, #取模
    ast.Pow: operator.pow, #幂运算
}


_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


_ALLOWED_FUNCTIONS = {
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
}


_ALLOWED_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
}


def calculate(expression: str) -> int | float:
    tree = ast.parse(expression, mode="eval")
    return _evaluate_expression(tree.body)


def _evaluate_expression(node: ast.AST) -> int | float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            raise ValueError("Boolean values are not allowed")

        if isinstance(node.value, int | float):
            return node.value

        raise ValueError("Only integer and float values are allowed")

    if isinstance(node, ast.Name):
        if node.id in _ALLOWED_CONSTANTS:
            return _ALLOWED_CONSTANTS[node.id]

        raise ValueError(f"Unsupported constant: {node.id}")

    if isinstance(node, ast.BinOp):
        operator_function = _BINARY_OPERATORS.get(type(node.op))
        if operator_function is None:
            raise ValueError("Unsupported binary operator")

        left = _evaluate_expression(node.left)
        right = _evaluate_expression(node.right)

        return operator_function(left, right)

    if isinstance(node, ast.UnaryOp):
        operator_function = _UNARY_OPERATORS.get(type(node.op))
        if operator_function is None:
            raise ValueError("Unsupported unary operator")

        value = _evaluate_expression(node.operand)
        return operator_function(value)

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only named functions are allowed")

        function = _ALLOWED_FUNCTIONS.get(node.func.id)
        if function is None:
            raise ValueError(f"Unsupported function: {node.func.id}")

        if node.keywords:
            raise ValueError("Keyword arguments are not allowed")

        arguments = [
            _evaluate_expression(argument)
            for argument in node.args
        ]

        return function(*arguments)

    raise ValueError("Unsupported expression")


def calculator_spec() -> ToolSpec:
    return ToolSpec(
        name="calculator",
        description=(
            "Evaluate a safe arithmetic expression using numbers, "
            "operators, approved functions, and constants."
        ),
        parameters={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": (
                        "An expression using numbers, +, -, *, /, //, %, **, "
                        "sqrt, abs, round, min, max, pi, and e."
                    ),
                }
            },
            "required": ["expression"],
            "additionalProperties": False,
        },
        handler=calculate,
    )

#查询___________________________________________________________________________________

_SEARCH_DOCUMENTS = [
    {
        "title": "Python dataclasses",
        "content": "dataclass 可以减少数据模型中的样板代码。",
    },
    {
        "title": "Python Protocol",
        "content": "Protocol 用来描述对象需要提供的行为接口。",
    },
    {
        "title": "Agent Loop",
        "content": "Agent Loop 通常包括调用模型、执行工具和继续推理。",
    },
]


def search(query: str) -> list[dict[str, str]]:
    normalized_query = query.strip().lower()

    if not normalized_query:
        return []

    return [
        document
        for document in _SEARCH_DOCUMENTS
        if normalized_query
        in f"{document['title']} {document['content']}".lower()
    ]


def search_spec() -> ToolSpec:
    return ToolSpec(
        name="search",
        description="Search a small built-in offline document collection.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The keyword to search for.",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=search,
    )

#todo_____________________________________________________________________________

def manage_todo(
    session: Session,
    action: str,
    text: str | None = None,
    todo_id: str | None = None,
) -> dict[str, object]:
    if action == "create":
        if not text or not text.strip():
            raise ValueError("text is required when creating a todo")

        todo = Todo(
            id=f"todo-{len(session.todos) + 1}",
            text=text.strip(),
        )
        session.todos.append(todo)

        return {
            "action": "created",
            "todo": {
                "id": todo.id,
                "text": todo.text,
                "status": todo.status,
            },
        }

    if action == "list":
        return {
            "action": "listed",
            "todos": [
                {
                    "id": todo.id,
                    "text": todo.text,
                    "status": todo.status,
                }
                for todo in session.todos
            ],
        }

    if action == "complete":
        if not todo_id:
            raise ValueError("todo_id is required when completing a todo")

        for todo in session.todos:
            if todo.id == todo_id:
                todo.status = "done"
                return {
                    "action": "completed",
                    "todo": {
                        "id": todo.id,
                        "text": todo.text,
                        "status": todo.status,
                    },
                }

        raise ValueError(f"Todo not found: {todo_id}")

    raise ValueError(f"Unsupported todo action: {action}")


def todo_spec(session: Session) -> ToolSpec:
    def todo_handler(
        action: str,
        text: str | None = None,
        todo_id: str | None = None,
    ) -> dict[str, object]:
        return manage_todo(
            session=session,
            action=action,
            text=text,
            todo_id=todo_id,
        )

    return ToolSpec(
        name="todo",
        description="Create, list, or complete todos in the current session.",
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "list", "complete"],
                    "description": "The todo operation to perform.",
                },
                "text": {
                    "type": "string",
                    "description": "The todo text, required for create.",
                },
                "todo_id": {
                    "type": "string",
                    "description": "The todo ID, required for complete.",
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
        handler=todo_handler,
    )

def validate_arguments(
    spec: ToolSpec,
    arguments: dict[str, object],
) -> None:
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be an object")

    schema = spec.parameters
    properties = schema.get("properties", {})

    for name in schema.get("required", []):
        if name not in arguments:
            raise ValueError(f"Missing required argument: {name}")

    if schema.get("additionalProperties") is False:
        for name in arguments:
            if name not in properties:
                raise ValueError(f"Unexpected argument: {name}")

    for name, value in arguments.items():
        rule = properties.get(name)
        if rule is None:
            continue

        if rule.get("type") == "string":
            if not isinstance(value, str):
                raise ValueError(f"Argument '{name}' must be a string")

        if "enum" in rule:
            if value not in rule["enum"]:
                raise ValueError(f"Argument '{name}' has an unsupported value")