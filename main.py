from tqdm import tqdm

from backend import DiscogsManager

class DownloadProgressBar(tqdm):
    def update_to(self, current, total):
        self.total = total
        self.update(current - self.n)

manager = DiscogsManager()

coll = manager.fetch_collection(force_update=True, progress_callback=DownloadProgressBar().update_to)
manager.fetch_artist_sort_names()
print(coll)