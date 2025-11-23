from tqdm import tqdm
import tabulate
from backend import DiscogsManager

class DownloadProgressBar(tqdm):
    def update_to(self, current, total):
        self.total = total
        self.update(current - self.n)

manager = DiscogsManager()

coll = manager.fetch_collection(force_update=False, progress_callback=DownloadProgressBar().update_to)
manager.fetch_artist_sort_names()
print(coll)
releases = manager.get_releases_paginated(page=0, page_size=600, sort_by='artist', desc=False, search_query="since")
print(tabulate.tabulate(releases[0], headers="keys"))  # Print first page of sorted releases