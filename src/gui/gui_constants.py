from gui.gui_classes import SidebarPage, IDFilterDefinition, StringFilterDefinition

PAGES = [
    SidebarPage(key=0, label='Collection', icon='list_alt', route='/'),
    SidebarPage(key=1, label='Settings', icon='settings', route='/settings'),
    # You can easily add more pages here without changing the methods
    # SidebarPage(key=2, label='New Page', icon='add', route='/new'),
]

FILTER_DEFINITIONS = [
    IDFilterDefinition(
        label='Artist Filter',
        data_list_attr='artist_list',
        manager_lookup='get_artist_id_by_name',
        filter_type='artist'
    ),
    IDFilterDefinition(
        label='Genre Filter',
        data_list_attr='genre_list',
        manager_lookup='get_genre_id_by_name',
        filter_type='genre'
    ),
    IDFilterDefinition(
        label='Style Filter',
        data_list_attr='style_list',
        manager_lookup='get_style_id_by_name',
        filter_type='style'
    ),
    IDFilterDefinition(
        label='Label Filter',
        data_list_attr='label_list',
        manager_lookup='get_label_id_by_name',
        filter_type='label'
    ),
    StringFilterDefinition(
        label='Format Filter',
        data_list_attr='format_list',
        attribute_name='format_selected_list'
    ),
]