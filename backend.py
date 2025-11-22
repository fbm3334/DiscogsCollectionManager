'''
backend.py

Backend logic for connecting to Discogs and fetching user collection data.
'''

import os
import time
from dataclasses import dataclass, field
import json
import re

import pandas as pd
import discogs_client as dc
import yaml

CLIENT_NAME = 'FBM3334Client/0.1'
REGEX_STRING = r'^\s*(?:the|a|el|la|los|las|un|una|le|la|les|un|une|il|lo|la|gli|le|ein|eine)\s+'

class DiscogsManager:
    '''
    Wrapper class for Discogs API interactions and data fetching.
    '''

    def __init__(self):
        '''
        Initialise DiscogsManager with settings and token loading.
        '''
        self.settings = {}
        self.pat = None
        self.client = None
        self.user = None
        self.df = pd.DataFrame()
        self.load_settings()
        self.load_token()

    def load_settings(self):
        '''
        Load settings from settings.yml file.
        '''
        try:
            with open('settings.yml', 'r') as file:
                self.settings = yaml.safe_load(file) or {}
        except FileNotFoundError:
            self.settings = {}
    
    def save_settings(self, new_settings):
        '''
        Save settings to settings.yml file.

        :param new_settings: Dictionary of settings to save.
        :type new_settings: dict
        '''
        self.settings.update(new_settings)
        with open('settings.yml', 'w') as file:
            yaml.dump(self.settings, file)
    
    def load_token(self):
        '''
        Load personal access token from secrets.yml file.
        '''
        try:
            with open('secrets.yml', 'r') as file:
                secrets = yaml.safe_load(file)
                self.pat = secrets.get('personal_access_token')
        except FileNotFoundError:
            self.pat = None
    
    def save_token(self, token):
        '''
        Save personal access token to secrets.yml file.

        :param token: Personal access token to save.
        :type token: str
        '''
        self.pat = token
        with open('secrets.yml', 'w') as file:
            file.write(f"personal_access_token: {token}\n")

    def connect_client(self):
        '''
        Connect to Discogs API using the personal access token.
        '''
        if not self.pat:
            raise ValueError("No Personal Access Token found.")
        self.client = dc.Client(CLIENT_NAME, user_token=self.pat)

    def identity(self):
        '''
        Fetch and return the authenticated user's identity.

        :return: User identity information.
        :rtype: discogs_client.models.User
        '''
        if not self.client:
            raise ValueError("Client not connected. Call connect_client() first.")
        self.user = self.client.identity()
        return self.user
    
    def get_collection_cache_filepath(self):
        '''
        Get the file path for the collection cache JSON file.

        :return: File path for collection cache.
        :rtype: str
        '''
        return os.path.join(
            self.settings.get('cache_folder', 'cache'),
            self.settings.get('collection_cache_file', 'collection.json')
        )
    
    def _fetch_release_data_helper(self, item: dc.CollectionItemInstance) -> dict:
        '''
        Helper function to retrieve the basic info of a release.

        :param item: Discogs collection item instance
        :type item: dc.CollectionItemInstance

        :return: Dictionary with release ID as key and list of release object and basic info as value.
        '''
        release_id = item.id
        release = self.client.release(release_id)
        basic_info = item.data.get('basic_information', None)
        return {release_id: [release, basic_info]}

        
    def fetch_user_release_data(self, progress_callback = None) -> dict:
        '''
        Fetch all release data from the user's Discogs collection.

        :param progress_callback: Optional callback function to report progress.
        :type progress_callback: function, optional
        
        :return: Dictionary of release data keyed by release ID.
        :rtype: dict
        '''
        release_data_dict = {}

        releases_to_process = self.user.collection_folders[0].releases
        total_releases = len(releases_to_process)

        for i, release in enumerate(releases_to_process):
            release_data = self._fetch_release_data_helper(release)
            release_data_dict.update(release_data)

            if progress_callback:
                progress_callback(i + 1, total_releases)

        return release_data_dict
    
    def create_release_dict(self, basic_info: dict, release: dc.Release) -> dict:
        '''
        Create a dictionary of relevant release information.

        :param basic_info: Basic information dictionary from Discogs API.
        :type basic_info: dict
        :param release: Discogs Release object.
        :type release: dc.Release
        :return: Dictionary of release information.
        :rtype: dict
        '''
        data = {
            'id': basic_info.get('id', ''),
            'master_id': basic_info.get('master_id', ''),
            'title': basic_info.get('title', ''),
            'release_year': basic_info.get('year', ''),
            'artists': ', '.join(artist.get('name', '') for artist in basic_info.get('artists', [])),
            'artist_list': [artist.get('name', '') for artist in basic_info.get('artists', [])],
            'first_artist_id': basic_info.get('artists', [{}])[0].get('id', '') if basic_info.get('artists') else '',
            'genre_list': basic_info.get('genres', []),
            'style_list': basic_info.get('styles', []),
            'format_list': [fmt.get('name', '') for fmt in basic_info.get('formats', [])],
            'label_list': [label.get('name', '') for label in basic_info.get('labels', [])],
            'catno_list': [label.get('catno', '') for label in basic_info.get('labels', [])],
            'url': f'https://www.discogs.com/release/{basic_info.get("id", "")}',
            'image_url': basic_info.get('cover_image', ''),
            'full_basic_info': basic_info,
            #'full_release_data': release
        }
        return data
    
    def fetch_collection(self, force_update=False, progress_callback=None):
        '''
        Fetch the user's Discogs collection, using cache if available and not forced to update.

        :param force_update: Whether to force update from API instead of using cache.
        :type force_update: bool
        :param progress_callback: Optional callback function to report progress.
        :type progress_callback: function, optional

        :return: DataFrame containing the user's collection data.
        :rtype: pd.DataFrame
        '''
        cache_filepath = self.get_collection_cache_filepath()

        # Check cache unless forced
        if not force_update and os.path.exists(cache_filepath):
            # Check that the update interval has not passed since last download
            # If not, then use the cached data and return
            update_interval = self.settings.get('update_interval_hours', 24) * 3600
            if (time.time() - os.path.getmtime(cache_filepath)) < update_interval:
                print("Using cached data.")
                self.df = pd.read_json(cache_filepath)
                return self.df

        # Download from API
        if not self.client:
            self.connect_client()
        if not self.user:
            self.identity()

        release_data_dict = self.fetch_user_release_data(progress_callback)

        # Process data into DataFrame
        data_list = []
        for release_id, (release, basic_info) in release_data_dict.items():
            if basic_info is None:
                continue

            data_entry = self.create_release_dict(basic_info, release)
            data_list.append(data_entry)

        self.df = pd.DataFrame(data_list)
        # Save to cache
        print("Saving data to cache.")
        os.makedirs(os.path.dirname(cache_filepath), exist_ok=True)
        self.df.to_json(cache_filepath, orient='records', lines=False)
        return self.df
    
    def get_unique_artist_ids(self):
        '''
        Get a set of unique artist IDs from the collection DataFrame.

        :return: Set of unique artist IDs.
        :rtype: set
        '''
        if self.df.empty:
            raise ValueError("DataFrame is empty. Fetch collection data first.")
        
        return set(self.df['first_artist_id'].dropna().unique())
    
    def get_artist_sort_name(self, artist_id):
        '''
        Get the sort name for a given artist ID.

        The Discogs artist object does not have the 'artist_sort' field accessible,
        but the release does, so we fetch the artist data from the first matching
        release with that artist ID.

        :param artist_id: Discogs artist ID.
        :type artist_id: int
        :return: Artist sort name.
        :rtype: str
        '''
        if not self.client:
            self.connect_client()
        
        df_filtered = self.df[self.df['first_artist_id'] == artist_id]
        if df_filtered.empty:
            return ''
        first_release_id = df_filtered.iloc[0]['id']
        release = self.client.release(first_release_id)
        release.refresh()
        return release.data.get('artists_sort', '')
    
    def check_artist_prefix(self, artist_name):
        '''
        Check if the artist name starts with a common prefix (e.g., "The", "A").

        :param artist_name: Name of the artist.
        :type artist_name: str
        :return: True if the name starts with a common prefix, False otherwise.
        :rtype: bool
        '''
        return re.match(REGEX_STRING, artist_name, re.IGNORECASE) is not None
    
    def load_sort_names_cache(self):
        '''
        Load artist sort names cache from JSON file.

        :return: Dictionary of artist IDs to sort names.
        :rtype: dict
        '''
        cache_filepath = os.path.join(
            self.settings.get('cache_folder', 'cache'),
            self.settings.get('artist_sort_cache_file', 'artist_sort_names.json')
        )
        if os.path.exists(cache_filepath):
            with open(cache_filepath, 'r') as file:
                return json.load(file)
        return {}
    
    def fetch_artist_sort_names(self, progress_callback=None):
        '''
        Fetch and cache artist sort names for all unique artists in the collection.

        :param progress_callback: Optional callback function to report progress.
        :type progress_callback: function, optional
        :return: DataFrame with updated artist sort names.
        :rtype: pd.DataFrame
        '''
        
        # Create a copy of the DataFrame to avoid modifying the original
        if self.df.empty:
            raise ValueError("DataFrame is empty. Fetch collection data first.")
        df_copy = self.df.copy()

        # Ensure the artist_sort_name column always exists so exports include it
        if 'artist_sort_name' not in df_copy.columns:
            df_copy['artist_sort_name'] = ''
        
        # Load existing cache
        sort_name_cache = self.load_sort_names_cache()

        # Prefill from cache
        for artist_id, sort_name in sort_name_cache.items():
            df_copy.loc[df_copy['first_artist_id'] == int(artist_id), 'artist_sort_name'] = sort_name

        # Fetch missing sort names
        missing_sort_ids = set(df_copy[df_copy['artist_sort_name'] == '']['first_artist_id'].unique())
        
        total_missing = len(missing_sort_ids)
        thorough = self.settings.get('thorough_name_fetch', False)
        for i, artist_id in enumerate(missing_sort_ids):
            if not thorough:
                series = df_copy[df_copy['first_artist_id'] == artist_id]
                first_artist_name = series.iloc[0]['artists']
                if not self.check_artist_prefix(first_artist_name):
                    sort_name_cache[str(artist_id)] = first_artist_name
                    df_copy.loc[df_copy['first_artist_id'] == artist_id, 'artist_sort_name'] = first_artist_name
                    if progress_callback:
                        progress_callback(i + 1, total_missing)
                    continue

            sort_name = self.get_artist_sort_name(artist_id)
            sort_name_cache[str(artist_id)] = sort_name
            df_copy.loc[df_copy['first_artist_id'] == artist_id, 'artist_sort_name'] = sort_name
            if progress_callback:
                progress_callback(i + 1, total_missing)
        
        # Save updated cache
        cache_filepath = os.path.join(
            self.settings.get('cache_folder', 'cache'),
            self.settings.get('artist_sort_cache_file', 'artist_sort_names.json')
        )
        os.makedirs(os.path.dirname(cache_filepath), exist_ok=True)
        with open(cache_filepath, 'w') as file:
            json.dump(sort_name_cache, file, indent=4)
        
        self.df = df_copy
        return self.df

    def clear_caches(self):
        '''
        Clear all cached files.
        '''
        cache_files = [
            self.get_collection_cache_filepath(),
            os.path.join(
                self.settings.get('cache_folder', 'cache'),
                self.settings.get('artist_sort_cache_file', 'artist_sort_names.json')
            )
        ]
        for filepath in cache_files:
            if os.path.exists(filepath):
                os.remove(filepath)
    
        print("All caches cleared.")
    