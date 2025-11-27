from tqdm import tqdm
import tabulate
from backend import DiscogsManager

class DownloadProgressBar(tqdm):
    def update_to(self, current, total):
        self.total = total
        self.update(current - self.n)

manager = DiscogsManager()

coll = manager.fetch_collection(progress_callback=DownloadProgressBar().update_to)
manager.fetch_artist_sort_names()
print(coll)
releases, _ = manager.get_releases_paginated(page=0, page_size=50, sort_by='artist', desc=False)
print(f"Total Releases: {len(releases)}")
print(tabulate.tabulate(releases, headers="keys"))  # Print first page of sorted releases