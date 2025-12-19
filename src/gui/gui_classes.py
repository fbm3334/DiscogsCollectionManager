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

@dataclass(frozen=True) # frozen=True makes the instances immutable
class IDFilterDefinition:
    label: str
    data_list_attr: str      # The name of the list attribute on self (e.g., 'artist_list')
    manager_lookup: str      # The manager method name (e.g., 'get_artist_id_by_name')
    attribute_name: str = 'Unused'
    filter_type: str         # The base name for the filter attribute (e.g., 'artist')
    callback_type: str = 'id'

@dataclass(frozen=True)
class StringFilterDefinition:
    label: str
    data_list_attr: str
    attribute_name: str      # The name of the instance attribute to update (e.g., 'format_selected_list')
    callback_type: str = 'string' # Identifier for the builder function
    manager_lookup: str = 'Unused'
    filter_type: str = 'Unused'