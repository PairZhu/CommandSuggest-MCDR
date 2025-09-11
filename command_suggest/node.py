from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


import mcdreforged.api.all as mcdr

class NodeTypes(Enum):
    LITERAL = mcdr.Literal
    NUMBER = mcdr.Number
    INTEGER = mcdr.Integer
    FLOAT = mcdr.Float
    TEXT = mcdr.Text
    QUOTABLE_TEXT = mcdr.QuotableText
    GREEDY_TEXT = mcdr.GreedyText
    BOOLEAN = mcdr.Boolean
    ENUMERATION = mcdr.Enumeration

    @classmethod
    def from_mcdr_node(cls, node_class: type) -> "NodeTypes":
        try:
            return cls(node_class)
        except ValueError:
            return cls.TEXT  # 默认类型


@dataclass
class CommandNode:
    name: str
    type: NodeTypes
    children: List["CommandNode"] = field(default_factory=list)
    suggestible: bool = False

    @classmethod
    def from_mcdr_node(cls, name: str, node: mcdr.AbstractNode) -> "CommandNode":
        node_type = NodeTypes.from_mcdr_node(node.__class__)
        suggestible = False
        if (
            isinstance(node, mcdr.ArgumentNode)
            and node._suggestion_getter.__code__.co_code
            != (lambda: []).__code__.co_code
        ):
            suggestible = True
        command_node = cls(name=name, type=node_type, suggestible=suggestible)
        for literal, literal_children in node._children_literal.items():
            if literal_children:
                child_node = cls.from_mcdr_node(literal, literal_children[0])
                command_node.children.append(child_node)
        for argument_child in node._children:
            child_name = getattr(argument_child, "_ArgumentNode__name", "<unknown>")
            child_node = cls.from_mcdr_node(child_name, argument_child)
            command_node.children.append(child_node)
        return command_node

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type.name,
            **({"children": [child.to_dict() for child in self.children]} if self.children else {}),
            **({"suggestible": self.suggestible} if self.suggestible else {}),
        }