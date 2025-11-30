from nicegui import ui, run
import yaml

from backend import DiscogsManager

manager = DiscogsManager()

INITIAL_PAGE_SIZE = 20
INITIAL_PAGE = 0


releases, num_releases = manager.get_releases_paginated(page=0, page_size=20, sort_by='artist', desc=False)
# Table code inspired by https://github.com/zauberzeug/nicegui/discussions/1903#discussioncomment-8251437

table_data = {
    'rows': releases,
    'pagination': {
        'page': INITIAL_PAGE,
        'rowsPerPage': INITIAL_PAGE_SIZE,
        'rowsNumber': num_releases,
    },
}

app_settings = manager.settings.copy()

search_query = ''

def save_settings():
    '''
    Callback function for save settings button.
    '''
    manager.save_settings(app_settings)
    ui.notify('Settings saved.')

@ui.refreshable
def _render_general_settings():
    '''
    Render the general settings.
    '''
    with ui.card_section().classes('w-full'):
        ui.label('General').classes('text-xl font-semibold text-primary')
        ui.number('Location Field Index',
                    value=app_settings['location_field'],
                    min=0, precision=0,
                    on_change=lambda e: app_settings.update({'location_field': int(e.value)}))
        ui.input('Output Folder',
                    value=app_settings['output_folder'],
                    on_change=lambda e: app_settings.update({'output_folder': e.value}))
        ui.input('Cache Folder',
                    value=app_settings['cache_folder'],
                    on_change=lambda e: app_settings.update({'cache_folder': e.value}))
        ui.input('Collection Cache File',
                    value=app_settings['collection_cache_file'],
                    on_change=lambda e: app_settings.update({'collection_cache_file': e.value}))
        
@ui.refreshable
def _render_automatic_update_settings():
    '''
    Render the automatic update settings.
    '''
    with ui.card_section().classes('w-full'):
        ui.label('Automatic Update').classes('text-xl font-semibold text-primary')
        ui.switch('Enable Auto Update',
                    value=app_settings['auto_update'],
                    on_change=lambda e: app_settings.update({'auto_update': e.value}))
        
        with ui.row().classes('items-center w-full'):
            ui.number('Update Interval (hours)',
                        value=app_settings['update_interval_hours'],
                        min=1, precision=0,
                        on_change=lambda e: app_settings.update({'update_interval_hours': int(e.value)})) \
                .classes('flex-grow')

@ui.refreshable     
def _render_export_type_settings():
    '''
    Render the export type settings.
    '''
    with ui.card_section().classes('w-full'):
        ui.label('Export Types').classes('text-xl font-semibold text-primary')
        with ui.row().classes('w-full justify-start gap-4'):
            ui.checkbox('CSV Export',
                        value=app_settings['export_types']['csv'],
                        on_change=lambda e: app_settings['export_types'].update({'csv': e.value}))
            ui.checkbox('Excel Export',
                        value=app_settings['export_types']['excel'],
                        on_change=lambda e: app_settings['export_types'].update({'excel': e.value}))
            
@ui.refreshable
def _render_name_refresh_settings():
    '''
    Render the name refresh settings.
    '''
    with ui.card_section().classes('w-full'):
        ui.label('Artist Sort Data').classes('text-xl font-semibold text-primary')
        ui.switch('Pull Artist Sort from Discogs',
                value=app_settings['pull_artist_sort_from_discogs']['enabled'], 
                on_change=lambda e: app_settings['pull_artist_sort_from_discogs'].update({'enabled': e.value}))
        ui.switch('Thorough Mode (Slower)',
                value=app_settings['pull_artist_sort_from_discogs']['thorough'], 
                on_change=lambda e: app_settings['pull_artist_sort_from_discogs'].update({'thorough': e.value}))
        ui.input('Artist Sort Cache File',
                value=app_settings['pull_artist_sort_from_discogs']['cache_file'], 
                on_change=lambda e: app_settings['pull_artist_sort_from_discogs'].update({'cache_file': e.value}))

@ui.refreshable
def settings_page():
    '''
    Renders the complete configuration form.
    '''
    with ui.card().classes('w-full max-w-2xl mx-auto shadow-lg'):
        ui.label('Settings').classes('text-2xl font-bold w-full mb-4')

        _render_general_settings()
        ui.separator()
        _render_automatic_update_settings()
        ui.separator()
        _render_export_type_settings()
        ui.separator()
        _render_name_refresh_settings()
    
        # Save button
        with ui.card_actions().classes('w-full justify-end'):
            # The save button now calls the function that writes to the file
            ui.button('Save Settings', on_click=save_settings, color='positive')

@ui.refreshable
def paginated_table():
    columns = [
        {'name': 'id', 'label': 'ID', 'field': 'id', 'sortable': True},
        {'name': 'artist_name', 'label': 'Artist', 'field': 'artist_name', 'sortable': True},
        {'name': 'title', 'label': 'Title', 'field': 'title', 'sortable': True},
        {'name': 'label_name', 'label': 'Label', 'field': 'label_name', 'sortable': True},
        {'name': 'catno', 'label': 'Cat No', 'field': 'catno', 'sortable': False},
        {'name': 'genres', 'label': 'Genres', 'field': 'genres', 'sortable': True},
        {'name': 'style_name', 'label': 'Styles', 'field': 'style_name', 'sortable': True},
        {'name': 'catno', 'label': 'Cat No', 'field': 'catno', 'sortable': False},
        {'name': 'year', 'label': 'Year', 'field': 'year', 'sortable': True},
        {'name': 'release_url', 'label': 'Discogs Link', 'field': 'release_url', 'sortable': False},
    ]
    table = ui.table(
        rows=table_data['rows'],
        title='Discogs Collection',
        columns=columns,
        pagination=table_data['pagination'],
        row_key='name'
    )
    table.add_slot('body-cell-release_url', '''
        <q-td :props="props">
            <u><a :href="props.value">Link</a></u>
        </q-td>
    ''')
    table.classes('w-full h-200 max-h-full virtual-scroll')
    table.on_select(lambda e: print(f'Selected rows: {e}'))
    table.on('request', do_pagination)

def get_full_count():
    _, count = manager.get_releases_paginated(page=0, page_size=1)
    table_data['pagination']['rowsNumber'] = count
    return count

def do_pagination(request):
    if isinstance(request, dict):
        new_pagination = request['args']['pagination']
    else:
        new_pagination = request.args['pagination']

    print(new_pagination)

    pagination = table_data['pagination']
    pagination.update(new_pagination)
    pagination_sort = new_pagination.get('sortBy', 'artist')

    pagination_sort = 'artist' if pagination_sort == 'artist_name' else pagination_sort

    pagination_desc = new_pagination.get('descending', False)

    if pagination_sort is None:
        pagination_sort = 'artist'
        pagination_desc = False

    new_rows, _ = manager.get_releases_paginated(
        page=pagination['page'] - 1,
        page_size=pagination['rowsPerPage'],
        sort_by=pagination_sort,
        desc=pagination_desc,
        search_query=search_query
    )
    print(new_rows)
    print(search_query)
    table_data['rows'] = new_rows
    paginated_table.refresh()

def search_callback(query):
    global search_query
    search_query = query.value
    table_data['pagination']['page'] = 1
    manual_request = {
        'args': {
            'pagination': {
                'page': 1,  # First page
                'rowsPerPage': table_data['pagination']['rowsPerPage'],
                'sortBy': table_data['pagination'].get('sortBy', 'artist'),
                'descending': table_data['pagination'].get('descending', False),
            }
        }
    }
    do_pagination(manual_request)
# --- Main Page Layout ---





ui.input('Search', on_change=search_callback).props('clearable rounded outlined dense')
paginated_table()

with ui.header().classes('items-center justify-between bg-gray-900 text-white shadow-lg'):
    ui.button(on_click=lambda: left_drawer.toggle(), icon='menu')
    ui.label('Discogs Manager Dashboard').classes('text-3xl font-extrabold')
    dark = ui.dark_mode()
    ui.switch('Dark mode').bind_value(dark)
    
with ui.left_drawer(top_corner=False, bottom_corner=True) as left_drawer:
    ui.label('Left Drawer')


get_full_count()
ui.run()
