from nicegui import ui, run
import yaml
from typing import List, Dict, Any, AnyStr

from backend import DiscogsManager


class DiscogsSorterGui:
    '''
    Discogs sorter GUI frontend class.
    '''
    INITIAL_PAGE_SIZE = 20
    INITIAL_PAGE = 0

    def __init__(self) -> None:
        '''
        Class initialisation method.
        '''
        self.manager = DiscogsManager()
        self.search_query = ''

        # Fetch initial releases
        self.releases, self.num_releases = self.manager.get_releases_paginated(
            page=0,
            page_size=20,
            sort_by='artist',
            desc=False
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

        self.artist_filter_ids = None
        self.build_ui()

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
            {'name': 'release_url', 'label': 'Discogs Link', 'field': 'release_url', 'sortable': False},
        ]
    
    def get_full_count(self) -> int:
        '''
        Get the count of releases and save the count (equal to the number of
        rows).

        :return: Count of releases.
        :rtype: int
        '''
        _, count = self.manager.get_releases_paginated(page=0, page_size=1)
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

        new_rows, _ = self.manager.get_releases_paginated(
            page=pagination['page'] - 1,
            page_size=pagination['rowsPerPage'],
            sort_by=pagination_sort,
            desc=pagination_desc,
            search_query=self.search_query,
            artist_id=self.artist_filter_ids
        )

        self.table_data['rows'] = new_rows
        self.paginated_table.refresh()

    def search_callback(self, query):
        '''
        Search callback function when the search box is updated.

        :param query: Search query
        '''
        self.search_query = query.value
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
        table.classes('w-full h-200 max-h-full virtual-scroll')
        table.on_select(lambda e: print(f'Selected rows: {e}'))
        table.on('request', self.do_pagination)

    def build_ui(self):
        '''
        Build the user interface.
        '''
        ui.input('Search', on_change=self.search_callback).props('clearable rounded outlined dense')
        self.paginated_table()

        with ui.header(elevated=True).classes('items-center justify-between bg-gray-900 text-white shadow-lg'):
            ui.button(on_click=lambda: left_drawer.toggle(), icon='menu')
            ui.label('Discogs Manager Dashboard').classes('text-3xl font-extrabold')
            dark = ui.dark_mode()
            ui.switch('Dark mode').bind_value(dark)
            
        with ui.left_drawer(top_corner=False, bottom_corner=True) as left_drawer:
            ui.select(
                self.artist_list, multiple=True, label='Artist Filter',
                with_input=True, on_change=self.artist_select_callback
                ).classes('w-70').props('use-chips')

        self.get_full_count()

if __name__ in {"__main__", "__mp_main__"}:
    gui = DiscogsSorterGui()
    ui.run()
