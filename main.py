'''
main.py
'''

# Python native imports
import os
import pprint
import re
import webbrowser

# Third-party imports
import discogs_client as dc
import yaml
import pandas as pd

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

def get_item_location(release: dc.Release):
    '''
    Get the location of a release from the user's collection.
    '''
    try:
        notes = release.notes
        loc = next((item['value'] for item in notes if item['field_id'] == location_field), '')
    except TypeError:
        loc = ''

    return loc

def collect_release_data(user):
    '''
    Collect release data from the user's Discogs collection.
    '''
    releases = []
    for item in user.collection_folders[0].releases:
        release = item.release
        data = {
            'id': release.id,
            'title': release.title,
            'year': release.year,
            'artists': ', '.join([artist.name for artist in release.artists]),
            'location': get_item_location(release),
            'url': release.url

        }
        releases.append(data)
    return pd.DataFrame(releases)

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

    # Collect release data
    df = collect_release_data(user)
    print(df)


if __name__ == '__main__':
    main()