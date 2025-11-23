from nicegui import ui, run

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

@ui.refreshable
def paginated_table():
    columns = [
        {'name': 'id', 'label': 'ID', 'field': 'id', 'sortable': False},
        {'name': 'artist_name', 'label': 'Artist', 'field': 'artist_name', 'sortable': False},
        {'name': 'title', 'label': 'Title', 'field': 'title', 'sortable': False},
        {'name': 'label_name', 'label': 'Label', 'field': 'label_name', 'sortable': False},
        {'name': 'catno', 'label': 'Cat No', 'field': 'catno', 'sortable': False},
        {'name': 'year', 'label': 'Year', 'field': 'year', 'sortable': False},
        {'name': 'thumb_url', 'label': 'Thumbnail', 'field': 'thumb_url', 'sortable': False},
        {'name': 'release_url', 'label': 'Release URL', 'field': 'release_url', 'sortable': False},
    ]
    table = ui.table(
        rows=table_data['rows'],
        title='Discogs Collection',
        columns=columns,
        pagination=table_data['pagination'],
    )
    table.on('request', do_pagination)

def get_full_count():
    _, count = manager.get_releases_paginated(page=0, page_size=1)
    table_data['pagination']['rowsNumber'] = count
    return count

def do_pagination(request):
    print(request)
    new_pagination = request.args['pagination']
    pagination = table_data['pagination']
    pagination.update(new_pagination)
    new_rows, _ = manager.get_releases_paginated(
        page=pagination['page'] - 1,
        page_size=pagination['rowsPerPage'],
        sort_by='artist',
        desc=False
    )
    print(new_rows)

    table_data['rows'] = new_rows
    paginated_table.refresh()
    print('TEST')

paginated_table()
get_full_count()
ui.run()