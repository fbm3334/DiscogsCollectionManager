'''
main.py
'''

# Python native imports
import os
import pprint
import pickle
import re
import webbrowser
import time
from dataclasses import dataclass, field
import argparse

# Third-party imports
import discogs_client as dc
import yaml
import pandas as pd
from tqdm import tqdm

# Constants
# Client name
CLIENT_NAME = 'FBM3334Client/0.1'

# Global variables
# Settings dictionary
settings = {}
# Personal access token for Discogs API
pat = None
# Location field (i.e. which custom field stores the location data)
location_field = None

# Dataclasses
@dataclass
class DiscogsPickleCache:
    '''
    Class to handle Discogs pickle cache.
    '''
    timestamp: float
    items: list

@dataclass
class DiscogsReleaseInstance:
    '''
    Class to hold Discogs release instance data.
    '''
    id: int
    release: dc.Release
    basic_info: dict | None = field(default=None)
    artists_sort: str | None = field(default=None)

# Argument parser
parser = argparse.ArgumentParser(description='Discogs Collection Sorter')
parser.add_argument('--force-update', action='store_true', help='Force update the collection data, ignoring cache.')

def get_personal_access_token():
    '''
    Load the personal access token from the secrets.yml file.
    '''
    global pat
    try:
        with open('secrets.yml', 'r') as file:
            secrets = yaml.safe_load(file)
            pat = secrets['personal_access_token']
    except FileNotFoundError:
        print("secrets.yml file not found. This file has been created - go to https://www.discogs.com/settings/developers to create a personal access token, add it to the file, and rerun the program.")
        with open('secrets.yml', 'w') as file:
            file.write("personal_access_token: YOUR_PERSONAL_ACCESS_TOKEN_HERE\n")
        exit(1)

def get_settings_yaml():
    '''
    Load settings from settings.yml file.
    '''
    global location_field
    global settings
    try:
        with open('settings.yml', 'r') as file:
            settings = yaml.safe_load(file)
            location_field = settings.get('location_field', None)
    except FileNotFoundError:
        print("settings.yml file not found.")
        exit(1)

def get_item_location(release: dc.CollectionItemInstance):
    '''
    Get the location of a release from the user's collection.
    '''
    global location_field
    if location_field is None:
        raise ValueError("location_field is not set. Please check your settings.yml file.")
    try:
        notes = release.notes
        loc = next((item['value'] for item in notes if item['field_id'] == location_field), '')
    except TypeError:
        loc = ''

    return loc

def get_collection_items(dc, user, force_update=False):
    '''
    Get all items in the user's Discogs collection.

    :param dc: Discogs client object
    :type dc: dc.Client
    :param user: Discogs user object
    :type user: dc.User
    :param force_update: Whether to force update the cache
    :type force_update: bool
    :return: List of collection items
    :rtype: list
    '''
    item_data = DiscogsPickleCache(timestamp=0.0, items=[])
    cache_count = 0

    if os.path.exists('cache/collection_items.pkl'):
        with open('cache/collection_items.pkl', 'rb') as f:
            item_data = pickle.load(f)
            print(f"Loaded {len(item_data.items)} items from cache.")
            print(f"Cache timestamp: {time.ctime(item_data.timestamp)}")
    else:
        os.makedirs('cache', exist_ok=True)
        item_data.timestamp = 0.0
        item_data.items = []

    # Check that the interval has passed first
    update_interval = settings.get('update_interval_hours', 24) * 3600
    if ((time.time() - item_data.timestamp < update_interval) or not settings.get('auto_update', True)) and force_update is False:
        print("Using cached data as update interval has not passed or auto updates are disabled.")
        return item_data.items
    else:
        print("Update interval has passed or update is forced, refreshing cache.")
        item_data.timestamp = time.time()
        item_data.items = []
        # Add to the cache
        for item in tqdm(user.collection_folders[0].releases):
            # Get the full release data
            release_id = item.id
            release = dc.release(release_id).fetch()
            basic_info = item.data.get('basic_information', None)
            artist_sort = release.data.get('artists_sort', None)
            item = DiscogsReleaseInstance(id=release_id, release=release, basic_info=basic_info, artists_sort=artist_sort)
            
            item_data.items.append(item)
            cache_count += 1

    print(f"Added {cache_count} new items to cache.")
    with open('cache/collection_items.pkl', 'wb') as f:
        pickle.dump(item_data, f, protocol=pickle.HIGHEST_PROTOCOL)
    return item_data.items

def create_release_dict(release: DiscogsReleaseInstance):
    '''
    Create a dictionary of release data from a DiscogsReleaseInstance.

    :param release: DiscogsReleaseInstance object
    :type release: DiscogsReleaseInstance
    :return: Dictionary of release data
    :rtype: dict
    '''
    basic_data = release.basic_info
    # Try to pull from basic info first
    if basic_data:
        data = {
            'id': basic_data.get('id', ''),
            'master_id': basic_data.get('master_id', ''),
            'title': basic_data.get('title', ''),
            'release_year': basic_data.get('year', ''),
            'artists': ', '.join(artist.get('name', '') for artist in basic_data.get('artists', [])),
            'genres': ', '.join(basic_data.get('genres', [])),
            'styles': ', '.join(basic_data.get('styles', [])),
            'format': ', '.join(fmt.get('name', '') for fmt in basic_data.get('formats', [])),
            'labels': ', '.join(label.get('name', '') for label in basic_data.get('labels', [])),
            'catnos': ', '.join(label.get('catno', '') for label in basic_data.get('labels', [])),
            'url': f'https://www.discogs.com/release/{basic_data.get("id", "")}',
            'image_url': basic_data.get('cover_image', '')
        }
    else:
        pass
    # Then add the rest from the release data
    data.update({
        'artists_sort': release.release.artists_sort
    })
    return data

def collect_release_data(items_list):
    '''
    Collect release data from the user's Discogs collection.
    '''
    release_data_list = []
    for item in items_list:
        # Fetch all release data at once to minimize API calls
        release = item.release
        release_data = release.data    # Access the raw data directly if possible
        
        # Get notes/location once
        #location = get_item_location(item)
    
        release_data_list.append(create_release_dict(item))
    return pd.DataFrame(release_data_list)

def df_exporter(df: pd.DataFrame, filename: str):
    '''
    Export the DataFrame to the supported formats.

    :param df: DataFrame to export
    :type df: pd.DataFrame
    :param filename: Base filename for the exported files
    :type filename: str
    '''
    output_folder = settings.get('output_folder', 'output')
    os.makedirs(output_folder, exist_ok=True)
    export_types = settings.get('export_types', {})
    if export_types.get('csv', False):
        csv_path = os.path.join(output_folder, f'{filename}.csv')
        df.to_csv(csv_path, index=False)
        print(f'Exported CSV to {csv_path}')
    if export_types.get('excel', False):
        excel_path = os.path.join(output_folder, f'{filename}.xlsx')
        df.to_excel(excel_path, index=False)
        print(f'Exported Excel to {excel_path}')

def main():
    '''
    Main function to sort Discogs collection based on location field.
    '''
    args = parser.parse_args()
    force_update = args.force_update

    # Load personal access token
    get_personal_access_token()

    # Load settings
    get_settings_yaml()

    # Initialize Discogs client
    d = dc.Client(CLIENT_NAME, user_token=pat)
    user = d.identity()

    # Get release data
    items_list = get_collection_items(d, user, force_update=force_update)
    d = None  # Free up memory
    df = collect_release_data(items_list)
    df_exporter(df, 'discogs_collection_sorted')

if __name__ == '__main__':
    main()