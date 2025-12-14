from datetime import datetime, timezone
import shutil
from typing import List, Dict, Any

from nicegui import ui, run
import tomlkit as tk
from tomlkit import TOMLDocument
from tomlkit.exceptions import NonExistentKey

from core.backend import DiscogsManager, PaginatedReleaseRequest
from gui.gui_classes import SidebarPage


PAGES = [
    SidebarPage(key=0, label='Collection', icon='list_alt', route='/'),
    SidebarPage(key=1, label='Settings', icon='settings', route='/settings'),
    # You can easily add more pages here without changing the methods
    # SidebarPage(key=2, label='New Page', icon='add', route='/new'),
]

class DiscogsSorterGui:
    '''
    Discogs sorter GUI frontend class.
    '''
    INITIAL_PAGE_SIZE = 20
    INITIAL_PAGxE = 0
    BLANKS_LABEL = '[Blanks]'

    def __init__(self, force_fetch: bool = False) -> None:
        '''
        Class initialisation method.

        :param force_fetch: Force a fetch from Discogs.
        :type force_fetch: bool
        '''
        self.manager = DiscogsManager()

        self.search_query = ''

        # Fetch initial releases
        initial_request = PaginatedReleaseRequest(
            page=0,
            page_size=20,
            sort_by='artist',
            desc=False
        )
        self.releases, self.num_releases = self.manager.get_releases_paginated(
            request=initial_request
        )

        # Table code inspired by https://github.com/zauberzeug/nicegui/discussions/1903#discussioncomment-8251437
        self.table_data = {
            'rows': self.releases,
            'pagination': {
                'page': self.INITIAL_PAGE,
                'rowsPerPage': self.INITIAL_PAGE_SIZE,
                'rowsNumber': self.num_releases,
            },
        }
        self.artist_dict = self.manager.get_all_artists()
        self.artist_list = []
        for artist in self.artist_dict:
            self.artist_list.append(artist.get('name', ''))

        self.genre_dict = self.manager.get_all_genres()
        self.genre_list = []
        for genre in self.genre_dict:
            self.genre_list.append(genre.get('name', ''))

        self.style_dict = self.manager.get_all_styles()
        self.style_list = []
        for style in self.style_dict:
            self.style_list.append(style.get('name', ''))

        self.label_dict = self.manager.get_all_labels()
        self.label_list = []
        for label in self.label_dict:
            self.label_list.append(label.get('name', ''))

        self.format_list = self.manager.get_unique_formats()

        self.entered_pat = None
        self.artist_filter_ids = None
        self.genre_filter_ids = None
        self.style_filter_ids = None
        self.label_filter_ids = None
        self.format_selected_list = None

        self.custom_field_data: Dict[int, List[str]] = self.get_all_custom_field_values()
        self.custom_field_filter_ids: dict[int, list[str]] | None = None 
        #self.user_settings_dialog = self.create_user_settings_dialog()
        
        self.refresh_flag = False
        self.refresh_progress_area = None
        self.progress_string = ""
        self.progress_stage = ""
        self.refresh_spinner = None
        
        self.config: TOMLDocument

        self.right_drawer = None
        self.current_page_key = 0

        self.load_toml_config()

        self.table: ui.table

        

    def load_toml_config(self):
        '''
        Load the custom configuraton if it exists, else copy the default
        config.
        '''
        # Try to load the config from config.toml
        try:
            with open('cache/config.toml', 'r', encoding='utf-8') as f:
                self.config = tk.load(f)
        except FileNotFoundError:
            # If the file isn't found, then copy over the default config
            # and load it.
            shutil.copyfile('defaultconfig.toml', 'cache/config.toml')
            with open('cache/config.toml', 'r', encoding='utf-8') as f:
                self.config = tk.load(f)
        
        print(self.config)

    def save_toml_config(self):
        '''
        Save the TOML config.
        '''
        with open('cache/config.toml', 'w', encoding='utf-8') as f:
            tk.dump(self.config, f)

    def get_columns(self) -> List[Dict[str, Any]]:
        '''
        Gets the columns of the table.

        :return: A list containing column dictionaries.
        :rtype: list
        '''
        column_list = [
            {'name': 'thumb', 'label': 'Art', 'field': 'thumb_url', 'sortable': False},
            {'name': 'id', 'label': 'ID', 'field': 'id', 'sortable': True},
            {'name': 'artist_name', 'label': 'Artist', 'field': 'artist_name', 'sortable': True, 
             'style': 'text-wrap: wrap'},
            {'name': 'title', 'label': 'Title', 'field': 'title', 'sortable': True, 
             'style': 'text-wrap: wrap'},
            {'name': 'label_name', 'label': 'Label', 'field': 'label_name', 'sortable': True, 
             'style': 'text-wrap: wrap'},
            {'name': 'catno', 'label': 'Cat No', 'field': 'catno', 'sortable': False, 
             'style': 'text-wrap: wrap'},
            {'name': 'genres', 'label': 'Genres', 'field': 'genres', 'sortable': True, 
             'style': 'text-wrap: wrap'},
            {'name': 'style_name', 'label': 'Styles', 'field': 'style_name', 'sortable': True, 
             'style': 'text-wrap: wrap'},
            {'name': 'year', 'label': 'Year', 'field': 'year', 'sortable': True},
            {'name': 'format', 'label': 'Format', 'field': 'format', 'sortable': True},
            {'name': 'release_url', 'label': 'Discogs Link', 'field': 'release_url', 'sortable': False},
        ]
        for custom_field in self.manager.get_custom_field_ids_set():
            # Try to get the user-set custon name, else use a default
            try:
                name = self.config['CustomFields'][f'field_{custom_field}']
            except NonExistentKey:
                name = f'Field {custom_field}'

            column_list.append(
                {'name': f'custom_{custom_field}',
                 'label': name,
                 'field': f'custom_{custom_field}',
                 'sortable': True, 
                 'style': 'text-wrap: wrap'}
            )
        return column_list
    
    def _toggle_columns(self, column: dict, visible: bool):
        '''
        Toggle columns to show/hide them.
        
        :param column: Column to toggle.
        :type column: dict
        :param visible: Visibility status
        :type visible: bool
        '''
        column['classes'] = '' if visible else 'hidden'
        column['headerClasses'] = '' if visible else 'hidden'
        self.table.update()
    
    def get_full_count(self) -> int:
        '''
        Get the count of releases and save the count (equal to the number of
        rows).

        :return: Count of releases.
        :rtype: int
        '''
        request = PaginatedReleaseRequest(
            page=0,
            page_size=1
        )
        _, count = self.manager.get_releases_paginated(request)
        self.table_data['pagination']['rowsNumber'] = count
        return count
    
    def do_pagination(self, request):
        '''
        Handles the table requests for searching, sorting and pagination,
        and updates the table data accordingly.

        :param request: Request for table
        '''
        if isinstance(request, dict):
            new_pagination = request['args']['pagination']
        else:
            new_pagination = request.args['pagination']

        pagination = self.table_data['pagination']
        pagination.update(new_pagination)
        pagination_sort = new_pagination.get('sortBy', 'artist')

        pagination_sort = 'artist' if pagination_sort == 'artist_name' else pagination_sort

        pagination_desc = new_pagination.get('descending', False)

        if pagination_sort is None:
            pagination_sort = 'artist'
            pagination_desc = False
        
        print('Filtr ID', self.label_filter_ids)

        request = PaginatedReleaseRequest(
            page=pagination['page'] - 1,
            page_size=pagination['rowsPerPage'],
            sort_by=pagination_sort,
            desc=pagination_desc,
            search_query=self.search_query,
            artist_ids=self.artist_filter_ids,
            genre_ids=self.genre_filter_ids,
            style_ids=self.style_filter_ids,
            label_ids=self.label_filter_ids,
            formats=self.format_selected_list,
            custom_field_filters=self.custom_field_filter_ids
        )
        print('Request update!', request)
        new_rows, count = self.manager.get_releases_paginated(
            request
        )

        self.table_data['pagination']['rowsNumber'] = count

        self.table_data['rows'] = new_rows
        self.paginated_table.refresh()

    def _send_manual_pagination_request(self):
        '''
        Send a manual pagination request.
        '''
        self.table_data['pagination']['page'] = 1
        manual_request = {
            'args': {
                'pagination': {
                    'page': 1,  # First page
                    'rowsPerPage': self.table_data['pagination']['rowsPerPage'],
                    'sortBy': self.table_data['pagination'].get('sortBy', 'artist'),
                    'descending': self.table_data['pagination'].get('descending', False),
                }
            }
        }
        self.do_pagination(manual_request)

    def search_callback(self, query):
        '''
        Search callback function when the search box is updated.

        :param query: Search query
        '''
        self.search_query = query.value
        self._send_manual_pagination_request()

    def _generic_select_callback(self, filter_type: str, id_lookup_method, query):
        '''
        A generic callback function for all ID-based selection filters 
        (Artist, Genre, Style, Label).

        :param filter_type: The base name of the filter ('artist', 'genre', 'style', 'label').
        :type filter_type: str
        :param id_lookup_method: The DiscogsManager method used to find the ID by name.
        :param query: The multiselect query object from NiceGUI (contains selected values).
        '''
        name_list = query.value
        id_list = []
        
        for name in name_list:
            # Calls self.manager.get_artist_id_by_name(name) or similar
            id_list.append(id_lookup_method(name)) 
        
        # Dynamically set the correct filter attribute
        # Example: If filter_type is 'artist', this sets self.artist_filter_ids
        attribute_name = f'{filter_type}_filter_ids'
        
        if id_list:
            setattr(self, attribute_name, id_list)
            print(f"Set {attribute_name}: {id_list}") # Replace with proper logging
        else:
            setattr(self, attribute_name, None)
        
        # Trigger the UI update
        self._send_manual_pagination_request()

    def _generic_string_callback(self, attribute_name: str, query):
        '''
        A generic callback function for string-based selection filters (e.g., Format).

        :param attribute_name: The name of the instance attribute to update (e.g., 'format_selected_list').
        :param query: The multiselect query object (contains selected values).
        '''
        selected_values = query.value

        if selected_values:
            # Set the attribute to the list of selected strings
            setattr(self, attribute_name, selected_values)
            print(f"Set {attribute_name}: {selected_values}") # Replace with proper logging
        else:
            # Clear the filter
            setattr(self, attribute_name, None)

        self._send_manual_pagination_request()

    def custom_field_select_callback(self, field_id: int, query):
        '''
        Callback function for custom field selection.

        :param field_id: The ID of the custom field (e.g., 1, 2, 3).
        :param query: The multiselect query object (contains selected values).
        '''
        selected_values = query.value # This is a list of strings

        if not self.custom_field_filter_ids:
            self.custom_field_filter_ids = {}

        if selected_values:
            # Store the selected values for this specific field ID
            self.custom_field_filter_ids[field_id] = selected_values
        elif field_id in self.custom_field_filter_ids:
            # If no values are selected, remove the filter for this field ID
            del self.custom_field_filter_ids[field_id]

        # If the dictionary is empty after deletion, set to None
        if not self.custom_field_filter_ids:
            self.custom_field_filter_ids = None

        self._send_manual_pagination_request()
    
    def get_all_custom_field_values(self) -> Dict[int, List[str]]:
        '''
        Fetches all unique values for each custom field from the DB, 
        including a special (Blanks) option for NULL/empty values.
        
        :returns: A dictionary mapping field_id (int) to a list of unique values (str).
        :rtype: Dict[int, List[str]]
        '''
        custom_field_data = {}
        with self.manager.get_db_connection() as conn:
            for field_id in self.manager.get_custom_field_ids_set():
                table_name = f'custom_field_{field_id}'
                
                # Fetch all values, including NULL/empty
                query = f'''
                SELECT DISTINCT
                    field_value
                FROM {table_name}
                ORDER BY field_value ASC;
                '''
                cursor = conn.execute(query)
                
                values = []
                has_blanks = False
                for row in cursor.fetchall():
                    value = row[0]
                    print(row, value)
                    if value is None or (isinstance(value, str) and value.strip() == ''):
                        # Found a blank or NULL value
                        has_blanks = True
                    else:
                        # Add non-blank values
                        values.append(value)

                
                values.insert(0, self.BLANKS_LABEL) # Add it at the start
                        
                custom_field_data[field_id] = values
        return custom_field_data

    @ui.refreshable
    def paginated_table(self):
        '''
        Function to render the paginated table.
        '''

        self.table = ui.table(
            rows=self.table_data['rows'],
            columns=self.get_columns(),
            pagination=self.table_data['pagination'],
            row_key='name'
        )
        self.table.add_slot('body-cell-release_url', '''
            <q-td :props="props">
                <u><a :href="props.value">Link</a></u>
            </q-td>
        ''')
        self.table.add_slot('body-cell-thumb', '''
            <q-td :props="props">
                <img :src="props.value" style="max-width: 50px; max-height: 50px;">
            </q-td>
        ''')

        self.table.classes('virtual-scroll h-[calc(100vh-200px)] w-full max-w-none')
        self.table.on('request', self.do_pagination)

    def discogs_connection_toggle_callback(self):
        '''
        Discogs connection toggle callback function.
        '''
        self.save_pat_callback()
        try:
            result = self.manager.toggle_discogs_connection()
            if result is True:
                ui.notify(f'Discogs connected as user {self.manager.user.username}.')
            else:
                ui.notify('Discogs disconnected.')
        except ValueError:
            ui.notify('No personal access token entered.', type='warning')
    
    def save_pat_callback(self):
        '''
        Save the new personal access token.
        '''
        if self.entered_pat is not None:
            self.manager.save_token(self.entered_pat.value)
    
    def user_settings_dialog_callback(self):
        '''
        User settings dialog callback.
        '''
        self.user_settings_dialog.open()
        
    @ui.refreshable
    def build_settings_menu(self):
        '''
        Build the settings menu with callbacks etc.
        '''
        with ui.row().classes('items-center justify-between w-70'):
                if self.manager.user is not None:
                    ui.label(f'Connected as {self.manager.user.username}')
                else:
                    ui.label('Disconnected from Discogs')
                ui.space()
                with ui.button(icon='settings'):
                    with ui.menu().props('auto-close'):
                        # Check whether Discogs is connected or not
                        if self.manager.user is not None:
                            ui.menu_item('Disconnect from Discogs', 
                                            on_click=self.discogs_connection_toggle_callback)
                        else:
                            ui.menu_item('Connect to Discogs', on_click=self.discogs_connection_toggle_callback)
                        ui.menu_item('User settings', on_click=self.user_settings_dialog_callback)
                        ui.menu_item('Refresh', on_click=self.start_refresh)

    async def start_refresh(self):
        '''
        Asynchronously start a refresh from the Discogs API.
        '''
        if self.refresh_flag is False:
            self.refresh_flag = True
            self.refresh_spinner.set_visibility(True)
            #self.refresh_progress_area.set_visibility(True)
            try:
                self.discogs_connection_toggle_callback()
            except ValueError:
                ui.notify('Could not refresh - go to User Settings \
                           to add a personal access token.', type='warning')
                #self.user_settings_dialog_callback()
                self.refresh_flag = False
                return
            ui.notify('Started refresh...')
            self.progress_stage = "Fetching collection"
            await run.io_bound(self.manager.fetch_collection, self.update_progress_string)
            ui.notify('Fetching artist sort names...')
            self.progress_stage = "Fetching artist sort names"
            await run.io_bound(self.manager.fetch_artist_sort_names, self.update_progress_string)
            ui.notify('Refresh complete.')
            self._send_manual_pagination_request()
            self.paginated_table.refresh()
            print('All done')
            self.refresh_flag = False
            self.config['Updates']['update_time'] = datetime.now(timezone.utc)
            self.save_toml_config()
            self.refresh_spinner.set_visibility(False)
            self.progress_string = ""
            self.footer_update_text.refresh()
            self.footer_text.refresh()

    async def start_auto_refresh(self):
        '''
        Start an auto-refresh if the conditions allow:

        - Auto-update is enabled.
        - Enough time has elapsed.
        '''
        if self.config['Updates']['auto_update'] is True:
            current_time = datetime.now(timezone.utc).timestamp()
            prev_time = self.config['Updates']['update_time'].timestamp()
            update_interval_secs = self.config['Updates']['update_interval'] * 60 * 60
            time_diff = current_time - prev_time

            if time_diff > update_interval_secs:
                self.config['Updates']['update_time'] = datetime.now(timezone.utc)
                self.save_toml_config()
                await self.start_refresh()
            else:
                print('Not auto updating.')
            

    def update_progress_string(self, current, total):
        '''
        Update the progress string.
        
        :param current: Current number.
        :param total: Total number.
        '''
        progress_percentage = (current / total) * 100.0
        self.progress_string = f'{self.progress_stage} ({progress_percentage:.1f}%)'
        self.footer_update_text.refresh()

    def build_filter_dropdowns(self):
        '''
        Build the filter dropdowns.
        '''
        ui.select(
            self.artist_list, multiple=True, label='Artist Filter',
            with_input=True, 
            on_change=lambda query: self._generic_select_callback('artist', self.manager.get_artist_id_by_name, query)
            ).classes('w-70').props('use-chips')
        ui.select(
            self.genre_list, multiple=True, label='Genre Filter',
            with_input=True, 
            on_change=lambda query: self._generic_select_callback('genre', self.manager.get_genre_id_by_name, query)
            ).classes('w-70').props('use-chips')
        
        ui.select(
            self.style_list, multiple=True, label='Style Filter',
            with_input=True, 
            on_change=lambda query: self._generic_select_callback('style', self.manager.get_style_id_by_name, query)
            ).classes('w-70').props('use-chips')
        
        ui.select(
            self.label_list, multiple=True, label='Label Filter',
            with_input=True,
            on_change=lambda query: self._generic_select_callback('label', self.manager.get_label_id_by_name, query)
            ).classes('w-70').props('use-chips')
        
        ui.select(
            self.format_list, multiple=True, label='Format Filter',
            with_input=True,
            on_change=lambda query: self._generic_string_callback('format_selected_list', query)
            ).classes('w-70').props('use-chips')
        
        for field_id, values in self.custom_field_data.items():
            # Get the user-defined name from the config (or default)
            try:
                name = self.config['CustomFields'][f'field_{field_id}']
            except NonExistentKey:
                name = f'Custom Field {field_id}'

            # Use a lambda function to pass the field_id to the callback
            ui.select(
                values, multiple=True, label=f'{name} Filter',
                with_input=True, on_change=lambda query, id=field_id: self.custom_field_select_callback(id, query)
                ).classes('w-70').props('use-chips')
        
    def navigate_refresh_left_drawer(self, page_key):
        '''
        Navigate to the next page and refresh the left drawer.
        
        :param page: Description
        '''
        self.current_page_key = page_key
        
        # Find the page data using the key
        target_page = next((p for p in PAGES if p.key == page_key), None)
        
        if target_page:
            ui.navigate.to(target_page.route)
        else:
            # Handle case where key is not found (optional)
            print(f"Error: Page with key {page_key} not found.")

        self.build_left_drawer.refresh()
    
    @ui.refreshable
    def build_left_drawer(self):
        '''
        Build the left drawer.
        '''
        selected_page_class = 'bg-gray-300 font-bold'
        deselected_page_class = ''

        with ui.list().classes('w-full'):
            # Loop through the list of SidebarPage objects
            for page in PAGES:
                is_selected = self.current_page_key == page.key
                
                with ui.item(on_click=lambda p=page: self.navigate_refresh_left_drawer(p.key)).classes(
                    selected_page_class if is_selected else deselected_page_class
                ):
                    with ui.item_section().props('avatar'):
                        ui.icon(page.icon)
                    with ui.item_section():
                        ui.item_label(page.label)

    def _build_discogs_access_token_settings(self):
        '''
        Build the Discogs access token settings.
        '''
        ui.label('Discogs Settings').classes('text-xl font-bold')
        ui.label('Discogs Access Token').classes('text-l font-bold')
        ui.markdown('Go to the [Discogs developers](https://www.discogs.com/settings/developers) settings page to generate a personal access token.')
        with ui.row().classes('items-center'):
            self.entered_pat = ui.input(label='Paste the personal access token here').classes('w-70')
            with ui.button_group():
                ui.button('Save', on_click=self.save_pat_callback)
                ui.button('Connect', on_click=self.discogs_connection_toggle_callback)

    def _build_update_settings(self):
        '''
        Build the update settings.
        '''
        ui.label('Update Settings').classes('text-xl font-bold')
        with ui.row().classes('items-center w-full'):
            ui.label('Auto-update')
            ui.space()
            ui.switch(on_change=lambda: self.save_toml_config()).bind_value(self.config['Updates'], 'auto_update')
        with ui.row().classes('items-center w-full'):
            ui.label('Auto-update interval (hours)')
            ui.space()
            ui.number(precision=0, on_change=lambda: self.save_toml_config()).bind_value(self.config['Updates'], 'update_interval')
        with ui.row().classes('items-center w-full'):
            ui.label('Update date/time display format -')
            ui.link('strftime.org gives a list of the codes', target='https://strftime.org', new_tab=True)
            ui.space()
            ui.textarea(on_change=lambda: self.save_toml_config()).bind_value(self.config['Updates'], 'update_time_display_format')

    def _build_custom_field_name_settings(self):
        '''
        Build the custom field name settings.
        '''
        # Check to see if CustomFields is in the config file first, and if not,
        # create it
        if 'CustomFields' not in self.config:
            new_table = tk.table(is_super_table=True)
            self.config.add('CustomFields', new_table)

        ui.label('Custom Field Names').classes('text-xl font-bold')
        for label in self.manager.get_custom_field_ids_set():
            with ui.row().classes('items-center w-full'):
                ui.label(f'Custom field {label} name')
                ui.space()
                ui.input(on_change=lambda: self.save_toml_config()).bind_value(self.config['CustomFields'], f'field_{label}')


    def _column_show_hide_callback(self, column: dict, visible: bool):
        '''
        Column show and hide callback - toggles the column as well as saves the
        config.
        
        :param column: Column to toggle.
        :type column: dict
        :param visible: Visibility status
        :type visible: bool
        '''
        print(column, visible)
        self._toggle_columns(column, visible)
        self.table.update()
        self.save_toml_config()
        pass

    def _make_column_config_list(self):
        '''
        Make the column configuration list.
        '''
        # Check if the table name is in the document and create if not
        table_name = 'ColumnVisibility'
        

        if table_name not in self.config:
            new_table = tk.table(is_super_table=True)
            self.config.add(table_name, new_table)

        config_table = self.config[table_name]

        for column in self.table.columns:
            # If the value exists, then create the key-value pairs
            print(column['field'])
            # If the field doesn't exist in the config table, create it, else
            # update the table accordingly
            if column['field'] not in config_table:
                config_table[column['field']] = True
            else:
                self._toggle_columns(column, config_table[column['field']])

    def _build_column_show_hide_settings(self):
        '''
        Build the column show/hide settings.
        '''
        self._make_column_config_list()
        for column in self.table.columns:
            table_name = 'ColumnVisibility'
            ui.checkbox(column['label'], on_change=lambda e, column=column: self._column_show_hide_callback(column, e.value)).bind_value(self.config[table_name], column['field'])

    def build_settings_page(self):
        '''
        Build the settings page.
        '''
        self._build_discogs_access_token_settings()
        ui.separator().classes('w-full')
        self._build_update_settings()
        ui.separator().classes('w-full')
        self._build_custom_field_name_settings()


    def build_root_elements(self):
        '''
        Build the root elements of the user interface (i.e. that will show on
        every page).
        '''
        with ui.header(elevated=True).classes('bg-gray-900 text-white shadow-lg'):
            ui.button(on_click=lambda: left_drawer.toggle(), icon='menu')
            ui.label('Discogs Collection Manager').classes('text-3xl font-extrabold')
            
        with ui.left_drawer() as left_drawer:
            self.build_left_drawer()

        with ui.right_drawer(value=False, top_corner=False, bottom_corner=False, elevated=True) as self.right_drawer:
            ui.button(on_click=self.right_drawer.hide, icon='close')
            self.build_filter_dropdowns()

        with ui.footer().classes('bg-gray-900 text-white shadow-lg items-center p-1'):
            self.footer_text()
            ui.space()
            self.footer_update_text()
            self.refresh_spinner = ui.spinner(color='white')
            self.refresh_spinner.set_visibility(False)

    @ui.refreshable
    def footer_text(self):
        '''
        Function for the footer text - updateable.
        '''
        formatted_string = self.config['Updates']['update_time'].strftime(self.config['Updates']['update_time_display_format'])
        ui.markdown(f'**Last update:** {formatted_string}')
        if self.manager.user is not None:
            ui.icon('link', size='24px').classes('p-0')
            ui.label(f'Connected to Discogs as {self.manager.user.username}')
        else:
            ui.icon('link_off', size='24px').classes('p-0')
            ui.label('Disconnected from Discogs')

    @ui.refreshable
    def footer_update_text(self):
        '''
        Function for footer update text - updateable.
        '''
        ui.label(f'{self.progress_string}')

    @ui.refreshable
    def _build_column_show_hide_button(self):
        '''
        Build a refreshable element for the column show/hide button.
        
        This is to avoid an AttributeError when the paginated table has not yet
        been created.
        '''
        try:
            with ui.button('Show/Hide Columns'):
                with ui.menu(), ui.column().classes('gap-0 p-2'):
                    self._build_column_show_hide_settings()
        except AttributeError:
            print('Show/hide button not added.')

    def build_main_ui(self):
        '''
        Build the main UI.
        '''
        with ui.row().classes('items-center justify-between content-between w-full bg-clip-padding'):
            ui.input('Search', on_change=self.search_callback).props('clearable rounded outlined dense')
            ui.button(icon='refresh', on_click=self.start_refresh)
            ui.space()
            self._build_column_show_hide_button()
            ui.button(text='Filters', icon='filter_alt', on_click=self.right_drawer.toggle)

        self.paginated_table()
        self.table.update()
        self._build_column_show_hide_button.refresh()

