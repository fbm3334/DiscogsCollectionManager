import argparse
from datetime import datetime, timezone
import shutil
from typing import List, Dict, Any

from nicegui import ui, run, app
import tomlkit as tk
from tomlkit import TOMLDocument

from backend import DiscogsManager, PaginatedReleaseRequest

class DiscogsSorterGui:
    '''
    Discogs sorter GUI frontend class.
    '''
    INITIAL_PAGE_SIZE = 20
    INITIAL_PAGE = 0

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
        self.user_settings_dialog = self.create_user_settings_dialog()
        
        self.refresh_flag = False
        self.refresh_progress_area = None
        self.progress_string = ""
        self.progress_stage = ""
        
        self.config: TOMLDocument

        self.load_toml_config()
        self.build_ui()


    def load_toml_config(self):
        '''
        Load the custom configuraton if it exists, else copy the default
        config.
        '''
        # Try to load the config from config.toml
        try:
            with open('config.toml', 'r', encoding='utf-8') as f:
                self.config = tk.load(f)
        except FileNotFoundError:
            # If the file isn't found, then copy over the default config
            # and load it.
            shutil.copyfile('defaultconfig.toml', 'config.toml')
            with open('config.toml', 'r', encoding='utf-8') as f:
                self.config = tk.load(f)
        
        print(self.config)

    def save_toml_config(self):
        '''
        Save the TOML config.
        '''
        with open('config.toml', 'w', encoding='utf-8') as f:
            tk.dump(self.config, f)

    def get_columns(self) -> List[Dict[str, Any]]:
        '''
        Gets the columns of the table.

        :return: A list containing column dictionaries.
        :rtype: list
        '''
        return [
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
            formats=self.format_selected_list
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

    def artist_select_callback(self, query):
        '''
        Callback function for artist selection.

        :param query: Artist selection query.
        '''
        
        name_list = query.value
        id_list = []
        
        for name in name_list:
            id_list.append(self.manager.get_artist_id_by_name(name))

        
        if len(id_list) < 1:
            self.artist_filter_ids = None
        else:
            self.artist_filter_ids = id_list
            print(self.artist_filter_ids)

        self._send_manual_pagination_request()
        

    def genre_select_callback(self, query):
        '''
        Callback function for genre selection.

        :param query: Genre selection query.
        '''
        genre_list = query.value
        id_list = []
        
        for genre in genre_list:
            id_list.append(self.manager.get_genre_id_by_name(genre))

        
        if len(id_list) < 1:
            self.genre_filter_ids = None
        else:
            self.genre_filter_ids = id_list

        self._send_manual_pagination_request()

    def style_select_callback(self, query):
        '''
        Callback function for style selection.

        :param query: Style selection query.
        '''
        style_list = query.value
        id_list = []
        
        for style in style_list:
            id_list.append(self.manager.get_style_id_by_name(style))

        
        if len(id_list) < 1:
            self.style_filter_ids = None
        else:
            self.style_filter_ids = id_list

        self._send_manual_pagination_request()

    def label_select_callback(self, query):
        '''
        Callback function for label selection.

        :param query: Style selection query.
        '''
        label_list = query.value
        id_list = []
        
        for label in label_list:
            id_list.append(self.manager.get_label_id_by_name(label))

        print(id_list)
        if len(id_list) < 1:
            self.label_filter_ids = None
        else:
            self.label_filter_ids = id_list

        self._send_manual_pagination_request()

    def format_select_callback(self, query):
        '''
        Callback function for format selection.

        :param query: Style selection query.
        '''
        format_list = query.value
        temp_format_list = []
        
        for format_sel in format_list:
            temp_format_list.append(format_sel)

        print(temp_format_list)
        if len(temp_format_list) < 1:
            self.format_selected_list = None
        else:
            self.format_selected_list = temp_format_list

        self._send_manual_pagination_request()

    @ui.refreshable
    def paginated_table(self):
        '''
        Function to render the paginated table.
        '''
        table = ui.table(
            rows=self.table_data['rows'],
            title='Discogs Collection',
            columns=self.get_columns(),
            pagination=self.table_data['pagination'],
            row_key='name'
        )
        table.add_slot('body-cell-release_url', '''
            <q-td :props="props">
                <u><a :href="props.value">Link</a></u>
            </q-td>
        ''')
        table.classes('w-full h-full virtual-scroll')
        table.on_select(lambda e: print(f'Selected rows: {e}'))
        table.on('request', self.do_pagination)

    def discogs_connection_toggle_callback(self):
        '''
        Discogs connection toggle callback function.
        '''
        result = self.manager.toggle_discogs_connection()
        if result is True:
            ui.notify(f'Discogs connected as user {self.manager.user.username}.')
        else:
            ui.notify('Discogs disconnected.')
        self.build_settings_menu.refresh()
        self.user_settings_dialog.close()

    def create_user_settings_dialog(self) -> ui.dialog:
        '''
        Create the user settings dialog.

        :return: The created, closed dialog.
        :rtype: ui.dialog
        '''
        with ui.dialog().classes('w-full') as dialog, ui.card():
            ui.label('User Settings').classes('text-xl font-bold')
            ui.separator()
            ui.label('Discogs Access Token').classes('text-l font-bold')
            ui.markdown('Go to the [Discogs developers](https://www.discogs.com/settings/developers) settings page to generate a personal access token.')
            with ui.row().classes('items-center'):
                self.entered_pat = ui.input(label='Paste the personal access token here').classes('w-70')
                with ui.button_group():
                    ui.button('Save', on_click=self.save_pat_callback)
                    ui.button('Connect', on_click=self.discogs_connection_toggle_callback)
            ui.button('Close', on_click=dialog.close)
            
        return dialog
    
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
                    ui.label(f'Disconnected from Discogs')
                ui.space()
                with ui.button(icon='settings'):
                    with ui.menu().props('auto-close') as menu:
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
            self.refresh_progress_area.set_visibility(True)
            try:
                self.discogs_connection_toggle_callback()
            except ValueError:
                ui.notify('Could not refresh - go to User Settings \
                           to add a personal access token.', type='warning')
                self.user_settings_dialog_callback()
                self.refresh_flag = False
                return
            self.build_settings_menu.refresh()
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
            self.refresh_progress_area.set_visibility(False)

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
        self.progress_area.refresh()

    @ui.refreshable
    def progress_area(self):
        '''
        Renders the progress area.
        '''
        with ui.row() as self.refresh_progress_area:
            ui.spinner()
            ui.label(self.progress_string)

    def build_ui(self):
        '''
        Build the user interface.
        '''
        with ui.row():
            ui.input('Search', on_change=self.search_callback).props('clearable rounded outlined dense')
            ui.markdown(f'**Last update:** {
                self.config['Updates']['update_time'].strftime(
                    self.config['Updates']['update_time_display_format']
                )
                }')

        self.paginated_table()

        with ui.header(elevated=True).classes('items-center justify-between bg-gray-900 text-white shadow-lg'):
            ui.button(on_click=lambda: left_drawer.toggle(), icon='menu')
            ui.label('Discogs Collection Manager').classes('text-3xl font-extrabold')
            dark = ui.dark_mode()
            ui.switch('Dark mode').bind_value(dark)
            
        with ui.left_drawer(top_corner=False, bottom_corner=True) as left_drawer:
            ui.select(
                self.artist_list, multiple=True, label='Artist Filter',
                with_input=True, on_change=self.artist_select_callback
                ).classes('w-70').props('use-chips')
            ui.select(
                self.genre_list, multiple=True, label='Genre Filter',
                with_input=True, on_change=self.genre_select_callback
                ).classes('w-70').props('use-chips')
            
            ui.select(
                self.style_list, multiple=True, label='Style Filter',
                with_input=True, on_change=self.style_select_callback
                ).classes('w-70').props('use-chips')
            
            ui.select(
                self.label_list, multiple=True, label='Label Filter',
                with_input=True, on_change=self.label_select_callback
                ).classes('w-70').props('use-chips')
            
            ui.select(
                self.format_list, multiple=True, label='Format Filter',
                with_input=True, on_change=self.format_select_callback
                ).classes('w-70').props('use-chips')

            ui.space()

            self.progress_area()

            self.refresh_progress_area.set_visibility(False)

            self.build_settings_menu()

        self.get_full_count()

if __name__ in {"__main__", "__mp_main__"}:
    parser = argparse.ArgumentParser()
    parser.add_argument('--server', action='store_true')
    args = parser.parse_args()
    
    server_mode = args.server
    if server_mode:
        print('Running in server mode...')
    gui = DiscogsSorterGui(force_fetch=False)
    ui.run(
        reload=False,
        favicon='💿',
        native=not(args.server),
        title='Discogs Collection Manager')
    
    
    app.timer(1, gui.start_auto_refresh, once=True)

