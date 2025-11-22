from tqdm import tqdm

from backend import DiscogsManager

class DownloadProgressBar(tqdm):
    def update_to(self, current, total):
        self.total = total
        self.update(current - self.n)

manager = DiscogsManager()

manager.clear_caches()
coll = manager.fetch_collection(force_update=True)
print(coll)