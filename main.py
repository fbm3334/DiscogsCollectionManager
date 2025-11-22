'''
main.py
'''

import os
import pprint
import pickle
import time
from dataclasses import dataclass, field
import argparse
import json
import re

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
# Match dictonary for artist sort
artist_sort_matches = {}

@dataclass
class DiscogsReleaseInstance:
    '''
    Class to hold Discogs release instance data.
    '''
    id: int
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


def fetch_release_data(client, item) -> dict:
    '''
    Fetch release data from Discogs API.

    :param dc: Discogs client object
    :type dc: dc.Client
    :param item: Discogs collection item
    :type item: dc.CollectionItemInstance
    :return: Dictionary with release ID as key and list of release object and basic info as value
    :rtype: dict
    '''
    release_id = item.id
    release = client.release(release_id)
    basic_info = item.data.get('basic_information', None)
    
    return {release_id: [release, basic_info]}

def user_collection_update_checker() -> bool:
    '''
    Checks whether the user's collection has been updated since the last cache.
    '''
    # Load cached data
    cache_filepath = os.path.join(
        settings.get('cache_folder', 'cache'),
        settings.get('collection_cache_file', 'collection.json')
    )
    if not os.path.exists(cache_filepath):
        return True  # No cache exists, so we need to update
    cache_mtime = os.path.getmtime(cache_filepath)
    # Here we would ideally check the user's collection last updated timestamp
    # However, Discogs API does not provide a direct way to get this information
    # So we will assume that if the cache is older than the value set in
    # settings, we should update.
    update_interval = settings.get('update_interval_hours', 24) * 3600
    if (time.time() - cache_mtime) > update_interval:
        return True
    return False

def get_discogs_data(dc, user):
    '''
    Fetch all release data from the user's Discogs collection.

    :param dc: Discogs client object
    :type dc: dc.Client
    :param user: Discogs user object
    :type user: dc.User
    :return: Dictionary with release ID as key and list of release object and basic info
    :rtype: dict
    '''

    release_data_dict = {}

    releases_to_process = user.collection_folders[0].releases
        
    for release in tqdm(releases_to_process, desc="Fetching release data"):
        discogs_release_instance = fetch_release_data(dc, release)
        release_data_dict.update(discogs_release_instance)

    return release_data_dict

    

def create_collection_df(dc, user, force_update=False) -> pd.DataFrame:
    '''
    Create a DataFrame of the user's Discogs collection.

    :param dc: Discogs client object
    :type dc: dc.Client
    :param user: Discogs user object
    :type user: dc.User
    :param force_update: Whether to force update the cache
    :type force_update: bool
    :return: DataFrame of collection data
    :rtype: pd.DataFrame
    '''

    # Get the collection dataframe from the cache
    collection_filepath = os.path.join(
        settings.get('cache_folder', 'cache'),
        settings.get('collection_cache_file', 'collection.json')
    )
    
    # Check if the DataFrame needs to be updated
    if user_collection_update_checker() or force_update:
        print("Collection has been updated or force update is set, refreshing data.")
        df_list = []
        dict_data = get_discogs_data(dc, user)
        for key, value in dict_data.items():
            release = value[0]
            basic_data = value[1]
            df_list.append(create_release_dict(release, basic_data))
        df = pd.DataFrame(df_list)
        # Save to cache
        os.makedirs(os.path.dirname(collection_filepath), exist_ok=True)
        df.to_json(collection_filepath, orient='records', lines=False)
        return df
            
    else:
        print("Using cached collection data.")
        df = pd.read_json(collection_filepath)
        return df

def create_release_dict(release, basic_data):
    '''
    Create a dictionary of release data from a DiscogsReleaseInstance.

    :param release: DiscogsReleaseInstance object
    :type release: DiscogsReleaseInstance
    :return: Dictionary of release data
    :rtype: dict
    '''
    data = {
        'id': basic_data.get('id', ''),
        'master_id': basic_data.get('master_id', ''),
        'title': basic_data.get('title', ''),
        'release_year': basic_data.get('year', ''),
        'artists': ', '.join(artist.get('name', '') for artist in basic_data.get('artists', [])),
        'first_artist_id': basic_data.get('artists', [{}])[0].get('id', '') if basic_data.get('artists') else '',
        'genres': ', '.join(basic_data.get('genres', [])),
        'styles': ', '.join(basic_data.get('styles', [])),
        'format': ', '.join(fmt.get('name', '') for fmt in basic_data.get('formats', [])),
        'labels': ', '.join(label.get('name', '') for label in basic_data.get('labels', [])),
        'catnos': ', '.join(label.get('catno', '') for label in basic_data.get('labels', [])),
        'url': f'https://www.discogs.com/release/{basic_data.get("id", "")}',
        'image_url': basic_data.get('cover_image', ''),
        'full_basic_data': basic_data,
        #'full_release_data': release
    }
    print(data)
    
    return data

def get_unique_artist_ids(df: pd.DataFrame) -> set:
    '''
    Get a set of unique artist IDs from the DataFrame.

    :param df: DataFrame containing collection data
    :type df: pd.DataFrame
    :return: Set of unique artist IDs
    :rtype: set
    '''
    artist_ids = set()
    for artist_id in df['first_artist_id'].dropna().unique():
        if artist_id != '':
            artist_ids.add(artist_id)
    return artist_ids

def get_artist_sort_name(df: pd.DataFrame, artist_id: int, dc_client: dc.Client) -> str:
    '''
    Get the artist sort name from Discogs API.

    The Discogs artist object does not have the 'artist_sort' field accessible,
    but the release does, so we fetch the artist data from the first matching
    release with that artist ID.

    :param df: DataFrame containing collection data
    :type df: pd.DataFrame
    :param artist_id: Discogs artist ID
    :type artist_id: int
    :param dc_client: Discogs client object
    :type dc_client: dc.Client
    :return: Artist sort name
    :rtype: str
    '''

    df_filtered = df[df['first_artist_id'] == artist_id]
    if df_filtered.empty:
        return ''
    first_release_id = df_filtered.iloc[0]['id']
    release = dc_client.release(first_release_id)
    release.refresh()
    return release.data.get('artists_sort', '')

def artist_prefix_searcher(artist_name: str) -> bool:
    '''
    Check if the artist name starts with a common prefix like "The", "A", or "An".

    :param artist_name: Name of the artist
    :type artist_name: str
    :return: True if the name starts with a prefix, False otherwise
    :rtype: bool
    '''
    REGEX_STRING = r'^\s*(?:the|a|el|la|los|las|un|una|le|la|les|un|une|il|lo|la|gli|le|ein|eine)\s+'
    return re.match(REGEX_STRING, artist_name, re.IGNORECASE) is not None
    
def artist_sort_name_fetcher(cache_filepath: str, items_list: pd.DataFrame, d: dc.Client, thorough: bool = False) -> pd.DataFrame:
    '''
    Fetch artist sort names and update the DataFrame.
    
    :param cache_filepath: Path to the cache file for artist sort names
    :type cache_filepath: str
    :param items_list: DataFrame containing collection data
    :type items_list: pd.DataFrame
    :param d: Discogs client object
    :type d: dc.Client
    :param thorough: Whether to perform a thorough check
    :type thorough: bool
    :return: Updated DataFrame with artist sort names
    :rtype: pd.DataFrame
    '''
    # Work on a copy to avoid unexpected chained-assignment issues
    items_list = items_list.copy()

    # Ensure the artist_sort_name column always exists so exports include it
    if 'artist_sort_name' not in items_list.columns:
        items_list['artist_sort_name'] = ''

    # Load existing artist sort dictionary (keys normalised to strings)
    if os.path.exists(cache_filepath):
        with open(cache_filepath, 'r') as f:
            sort_dict = json.load(f)
            # normalize existing keys to strings
            sort_dict = {str(k): v for k, v in sort_dict.items()}
    else:
        sort_dict = {}

    # Pre-fill the DataFrame with any cached sort names so the column exists
    if sort_dict:
        for k, v in sort_dict.items():
            try:
                aid = str(k)
            except Exception:
                continue
            # Use string comparisons to avoid int/float/string dtype mismatches
            items_list.loc[items_list['first_artist_id'].astype(str) == aid, 'artist_sort_name'] = v

    # Get the unique artist IDs from the DataFrame
    unique_ids = get_unique_artist_ids(items_list)

    # Get the list of IDs not already in the sort dictionary
    ids_not_in_sort_dict = [aid for aid in unique_ids if str(aid) not in sort_dict]

    # Get the missing IDs and update the sort dictionary
    for aid in tqdm(ids_not_in_sort_dict, desc="Fetching artist sort names"):
        # If thorough checking is disabled, skip artists whose names start with common prefixes
        if not thorough:
            # For each unique ID, get the artist name (first match)
            # Use string comparison to be robust against dtype differences
            series = items_list.loc[items_list['first_artist_id'].astype(str) == str(aid), 'artists']
            artist_name = series.iloc[0] if not series.empty else ''
            # If the artist name does not start with the prefix, then use the existing name as the sort name
            if artist_name and not artist_prefix_searcher(artist_name):
                sort_dict[str(aid)] = artist_name
                # Append the sort name to the DataFrame (string compare)
                items_list.loc[items_list['first_artist_id'].astype(str) == str(aid), 'artist_sort_name'] = artist_name
                continue

        # Otherwise fetch the sort name from Discogs
        sort_name = get_artist_sort_name(items_list, aid, d)
        sort_dict[str(aid)] = sort_name
        # Append the sort name to the DataFrame (string compare)
        items_list.loc[items_list['first_artist_id'].astype(str) == str(aid), 'artist_sort_name'] = sort_name

    # Save the updated sort dictionary to cache (keys as strings)
    with open(cache_filepath, 'w') as f:
        json.dump(sort_dict, f, ensure_ascii=False, indent=2)

    return items_list

def df_exporter(df: pd.DataFrame, filename: str):
    '''
    Export the DataFrame to the supported formats.

    :param df: DataFrame to export
    :type df: pd.DataFrame
    :param filename: Base filename for the exported files
    :type filename: str
    '''
    df = df.drop(columns=['full_basic_data', 'full_release_data'], errors='ignore')
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
    items_list = create_collection_df(d, user, force_update=force_update)
    
    artist_sort_settings = settings.get('pull_artist_sort_from_discogs', {})
    artist_sort_enabled = artist_sort_settings.get('enabled', False)
    artist_sort_dict_file = artist_sort_settings.get('cache_file', 'artist_sort_cache.json')
    thorough_check = artist_sort_settings.get('thorough', False)
    artist_sort_dict_path = os.path.join(
        settings.get('cache_folder', 'cache'),
        artist_sort_dict_file
    )
    # If artist sorting data is pulled from Discogs
    if artist_sort_enabled:
        items_list = artist_sort_name_fetcher(artist_sort_dict_path, items_list, d, thorough=thorough_check)
    
    # Sort the DataFrame by artist sort name and then title
    if 'artist_sort_name' in items_list.columns:
        items_list = items_list.sort_values(by=['artist_sort_name', 'title'], ascending=[True, True])


    # Export DataFrame
    df_exporter(items_list, 'discogs_collection')

if __name__ == '__main__':
    main()