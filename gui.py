from nicegui import ui, run

from backend import DiscogsManager

manager = DiscogsManager()

INITIAL_PAGE_SIZE = 20
INITIAL_PAGE = 0

releases, num_releases = manager.get_releases_paginated(page=0, page_size=20, sort_by='artist', desc=False)
print(num_releases)

collection_table = ui.table(
    rows=releases,
    title='Discogs Collection',
    columns=[
        {'name': 'id', 'label': 'ID', 'field': 'id', 'sortable': False},
        {'name': 'artist_name', 'label': 'Artist', 'field': 'artist_name', 'sortable': False},
        {'name': 'title', 'label': 'Title', 'field': 'title', 'sortable': False},
        {'name': 'label_name', 'label': 'Label', 'field': 'label_name', 'sortable': False},
        {'name': 'catno', 'label': 'Cat No', 'field': 'catno', 'sortable': False},
        {'name': 'year', 'label': 'Year', 'field': 'year', 'sortable': False},
        {'name': 'thumb_url', 'label': 'Thumbnail', 'field': 'thumb_url', 'sortable': False},
        {'name': 'release_url', 'label': 'Release URL', 'field': 'release_url', 'sortable': False},
    ],
    pagination={'rowsPerPage': INITIAL_PAGE_SIZE,'rowsNumber': num_releases},
)

ui.run()