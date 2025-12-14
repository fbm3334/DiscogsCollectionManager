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

STATIC_COLUMNS = [
    {'name': 'thumb', 'label': 'Art', 'field': 'thumb_url', 'sortable': False},
    {'name': 'id', 'label': 'ID', 'field': 'id', 'sortable': True},
    {'name': 'artist_name', 'label': 'Artist', 'field': 'artist_name', 'sortable': True, 'style': 'text-wrap: wrap'},
    {'name': 'title', 'label': 'Title', 'field': 'title', 'sortable': True, 'style': 'text-wrap: wrap'},
    {'name': 'label_name', 'label': 'Label', 'field': 'label_name', 'sortable': True, 'style': 'text-wrap: wrap'},
    {'name': 'catno', 'label': 'Cat No', 'field': 'catno', 'sortable': False, 'style': 'text-wrap: wrap'},
    {'name': 'genres', 'label': 'Genres', 'field': 'genres', 'sortable': True, 'style': 'text-wrap: wrap'},
    {'name': 'style_name', 'label': 'Styles', 'field': 'style_name', 'sortable': True, 'style': 'text-wrap: wrap'},
    {'name': 'year', 'label': 'Year', 'field': 'year', 'sortable': True},
    {'name': 'format', 'label': 'Format', 'field': 'format', 'sortable': True},
    {'name': 'release_url', 'label': 'Discogs Link', 'field': 'release_url', 'sortable': False},
]