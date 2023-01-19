from typing import TypedDict, List


class VNodeChild(TypedDict):
    children: list
    props: dict

class VNode(TypedDict):
    children: List[VNodeChild]
    type: str

