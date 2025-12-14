import re

import discogs_client as dc
import yaml
from core.database_manager import DatabaseManager


class DiscogsConn:
    '''
    Wrapper class for managing connections to the Discogs database.
    '''
    CLIENT_NAME = 'FBM3334Client/0.3'
    REGEX_STRING = r'^\s*(?:the|a|el|la|los|las|un|una|le|la|les|un|une|il|lo|la|gli|le|ein|eine)\s+'

    def __init__(self):
        self.pat = None
        self.custom_ids: set
        self.db = DatabaseManager()
        self.user = None
        self.client = None
        pass

    def load_token(self):
        '''
        Load personal access token from secrets YAML file.
        '''
        try:
            with open('secrets.yml', 'r', encoding='utf-8') as file:
                secrets = yaml.safe_load(file)
                self.pat = secrets.get('personal_access_token')
        except FileNotFoundError:
            self.pat = None

    def save_token(self, token):
        '''
        Save personal access token to secrets YAML file.

        :param token: Personal access token
        '''
        self.pat = token
        with open('secrets.yml', 'w', encoding='utf-8') as file:
            file.write(f"personal_access_token: {token}\n")

    def connect_client(self):
        '''
        Connect to Discogs API using the personal access token.
        '''
        if not self.pat:
            raise ValueError("No Personal Access Token found.")
        self.client = dc.Client(self.CLIENT_NAME, user_token=self.pat)

    def identity(self):
        '''
        Fetch and return the user identity from Discogs.

        :return: Discogs user identity.
        '''
        if not self.client:
            raise ValueError("Client not connected.")
        self.user = self.client.identity()
        return self.user
    
    def get_custom_field_ids(self, releases_list: list[dc.CollectionItemInstance]) -> set:
        '''
        Extract custom field IDs from a list of CollectionItemInstance objects.

        :param releases_list: List of CollectionItemInstance objects
        :type releases_list: list[dc.CollectionItemI`nstance]
        :return: Set of custom field IDs
        :rtype: set
        '''
        custom_field_ids = set()
        for item in releases_list:
            if item.notes:
                for note in item.notes:
                    custom_field_id = note['field_id']
                    print(custom_field_id)
                    custom_field_ids.add(custom_field_id)
        return custom_field_ids
    
    def fetch_collection(self, progress_callback = None):
        '''
        Fetches the collection from Discogs and updates the databases.
        :param progress_callback: Optional callback to report progress
        :type progress_callback: callable

        :return: List of collection items.
        :rtype: list
        '''
        output_list = []
        if not self.client:
            self.connect_client()
        if not self.user:
            self.identity()

        print("Fetching from Discogs API...")
        releases_to_process = self.user.collection_folders[0].releases
        total_releases = len(releases_to_process)

        custom_field_ids = set()


        for i, item in enumerate(releases_to_process):
            # item.data contains exactly what we need
            # We don't need self.client.release() usually, unless we need extra deep data
            basic_info = item.data.get('basic_information')
            if basic_info:
                output_list.append((basic_info, item.notes))

            if item.notes:
                for note in item.notes:
                    custom_field_id = note['field_id']
                    custom_field_ids.add(custom_field_id)
            
            if progress_callback:
                progress_callback(i + 1, total_releases)

        self.custom_ids = custom_field_ids
        
        self.db.add_releases_to_db(output_list)
    
    def _fetch_sort_name_from_api(self, artist_id, default_name):
        '''
        Uses the Discogs client to find the accurate sort name.

        :param artist_id: Artist ID
        :param default_name: Default name
        :return: Sort name
        '''
        
        # Fetch artist details from API (Rate limits apply)
        artist_obj = self.client.artist(artist_id)
        
        # Find a related release to get the 'artists_sort' field

        first_release_id = self.db.get_first_release_from_artist(artist_id)
        
        if first_release_id is not None:
            release = self.client.release(first_release_id[0])
            release.refresh() # Ensure full data
            return release.data.get('artists_sort', default_name)
        else:
            return default_name
        
    def _check_artist_prefix(self, artist_name):
        '''
        Check the artist prefix against a regular expression,
        '''
        return re.match(self.REGEX_STRING, artist_name, re.IGNORECASE) is not None
        
    def _determine_sort_name(self, artist_id, artist_name):
        '''
        Determines the correct sort name, using simple check or API fetch.

        :param conn: Database connection.
        :param artist_id: Artist ID.
        :param artist_name: Artist name.
        '''
        thorough = False
        
        # 1. Simple Check (Fast Path)
        if not thorough and not self._check_artist_prefix(artist_name):
            return artist_name  # Sort name is the regular name
        
        # 2. API Fetch (Slow Path)
        try:
            return self._fetch_sort_name_from_api(artist_id, artist_name)
        except Exception as e:
            print(f"Error fetching sort name for {artist_name}: {e}")
            return artist_name # Fallback to regular name on error
        
    def _process_and_batch_updates(self, artists_to_check, progress_callback):
        '''
        Iterates through artists, determines sort names, and commits in batches.

        :param artists_to_check: Artists to check
        :param progress_callback: Optional progress callback
        '''
        
        total = len(artists_to_check)
        updates = [] # Store tuples (sort_name, id)
        
        for i, row in enumerate(artists_to_check):
            a_id, a_name = row['id'], row['name']
            
            # Determine the sort name using the refactored helper
            sort_name = self._determine_sort_name(a_id, a_name)
            updates.append((sort_name, a_id))
            
            if progress_callback:
                progress_callback(i + 1, total)
                
            # Batch update every 10
            if len(updates) >= 10:
                self.db.commit_batch_updates(updates)
                updates = []
                
        # Commit remaining
        if updates:
            self.db.commit_batch_updates(updates)

    def fetch_artist_sort_names(self, progress_callback=None):
        '''
        Coordinates the fetching and updating of artist sort names.

        :param progress_callback: Optional progress callback function.
        '''       
        artists_to_check = self.db.get_artists_missing_sort_name()
        if not artists_to_check:
            return
            
        if not self.client:
            self.connect_client()
        
        self._process_and_batch_updates(artists_to_check, progress_callback)

    def toggle_discogs_connection(self) -> bool:
        '''
        Toggle the Discogs connection and return the status as a boolean.

        :return: Boolean of the Discogs connection status.
        :rtype: bool
        '''

        if self.user is not None:
            self.user = None
            return False
        else:
            # Connect to API
            self.connect_client()
            self.identity()
            if self.user is not None:
                return True
            
        return False