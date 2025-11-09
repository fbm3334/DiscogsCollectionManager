'''
main.py
'''

# Python native imports
import os
import pprint
import pickle
import re
import webbrowser

# Third-party imports
import discogs_client as dc
import yaml
import pandas as pd
from tqdm import tqdm

# Constants
# Client name
CLIENT_NAME = 'FBM3334Client/0.1'

# Global variables
# Personal access token for Discogs API
pat = None
# Location field (i.e. which custom field stores the location data)
location_field = None

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
    try:
        with open('settings.yml', 'r') as file:
            settings = yaml.safe_load(file)
            location_field = settings.get('location_field', None)
    except FileNotFoundError:
        print("settings.yml file not found. This file has been created with default settings. Please edit it and rerun the program.")
        with open('settings.yml', 'w') as file:
            file.write("location_field: 4\n")
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

def get_collection_items(user):
    '''
    Get all items in the user's Discogs collection.
    '''
    cache_count = 0

    if os.path.exists('cache/collection_items.pkl'):
        with open('cache/collection_items.pkl', 'rb') as f:
            items = pickle.load(f)
            print(f"Loaded {len(items)} items from cache.")
    else:
        items = []
    
    # Check that the item does not already exist in the cache
    for item in tqdm(user.collection_folders[0].releases):
        if item not in items:
            items.append(item)
            cache_count += 1

    print(f"Added {cache_count} new items to cache.")
    with open('cache/collection_items.pkl', 'wb') as f:
        pickle.dump(items, f, protocol=pickle.HIGHEST_PROTOCOL)
    return items

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
        location = get_item_location(item)
        
        data = {
            'id': release_data.get('id', ''),
            'title': release_data.get('title', ''),
            'year': release_data.get('year', ''),
            'artists': ', '.join(artist.get('name', '') for artist in release_data.get('artists', [])),
            'location': location,
            'url': release_data.get('uri', '')
        }
        release_data_list.append(data)
    return pd.DataFrame(release_data_list)

def main():
    '''
    Main function to sort Discogs collection based on location field.
    '''
    global location_field

    # Load personal access token
    get_personal_access_token()

    # Load settings
    get_settings_yaml()

    # Initialize Discogs client
    d = dc.Client(CLIENT_NAME, user_token=pat)
    user = d.identity()

    # Get release data
    items_list = get_collection_items(user)
    df = collect_release_data(items_list)


if __name__ == '__main__':
    main()