'''
Docstring for src.gui.gui_classes
'''
from dataclasses import dataclass

@dataclass
class SidebarPage:
    """Represents a page/item in the sidebar."""
    key: int
    label: str
    icon: str
    route: str