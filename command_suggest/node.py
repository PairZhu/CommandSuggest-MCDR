import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


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

    @staticmethod
    def _is_suggestible(node: mcdr.AbstractNode) -> bool:
        return (
            isinstance(node, mcdr.ArgumentNode)
            and node._suggestion_getter.__code__.co_code
            != (lambda: []).__code__.co_code
        )

    @staticmethod
    def _iter_mcdr_children(
        node: mcdr.AbstractNode,
    ) -> Iterable[Tuple[str, mcdr.AbstractNode]]:
        for literal, literal_children in node._children_literal.items():
            if literal_children:
                yield literal, literal_children[0]
        for argument_child in node._children:
            yield getattr(argument_child, "_ArgumentNode__name", "<unknown>"), argument_child

    @staticmethod
    def _warn_cycle(
        logger: Optional[logging.Logger], path: Tuple[str, ...], child_name: str
    ) -> None:
        if logger is not None:
            logger.warning(
                "Detected cyclic command node reference, skipping branch: %s -> %s",
                " ".join(path),
                child_name,
            )

    @classmethod
    def from_mcdr_node(
        cls,
        name: str,
        node: mcdr.AbstractNode,
        logger: Optional[logging.Logger] = None,
        path: Tuple[str, ...] = (),
        visiting: Optional[Set[int]] = None,
    ) -> "CommandNode":
        if visiting is None:
            visiting = set()

        node_id = id(node)
        current_path = (*path, name)
        command_node = cls(
            name=name,
            type=NodeTypes.from_mcdr_node(node.__class__),
            suggestible=cls._is_suggestible(node),
        )
        visiting.add(node_id)
        try:
            for child_name, child in cls._iter_mcdr_children(node):
                if id(child) in visiting:
                    cls._warn_cycle(logger, current_path, child_name)
                    continue
                command_node.children.append(
                    cls.from_mcdr_node(child_name, child, logger, current_path, visiting)
                )
        finally:
            visiting.remove(node_id)
        return command_node

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type.name,
            **({"children": [child.to_dict() for child in self.children]} if self.children else {}),
            **({"suggestible": self.suggestible} if self.suggestible else {}),
        }
