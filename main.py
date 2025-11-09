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
            'format': ', '.join(fmt.get('name', '') for fmt in release_data.get('formats', [])),
            'location': location,
            'url': f'https://www.discogs.com/release/{release_data.get('id', '')}' if release_data else '',
            'image_url': release_data.get('cover_image', '')
        }
        release_data_list.append(data)
    return pd.DataFrame(release_data_list)

def generate_latex_pdf(df: pd.DataFrame, output_file: str):
    '''
    Generate a LaTeX PDF with a table from the releases DataFrame.
    '''
    from pylatex import Document, Section, Subsection, Command
    from pylatex.utils import NoEscape, bold

    doc = Document()
    with doc.create(Section('Discogs Collection')):
        with doc.create(Subsection('Releases')):
            # Create table header
            header = ['ID', 'Title', 'Year', 'Artists', 'Format', 'Location', 'URL']
            table_spec = ' | '.join(['l'] * len(header))
            doc.append(NoEscape(r'\begin{tabular}{' + table_spec + r'}'))
            doc.append(NoEscape(r'\hline'))
            doc.append(NoEscape(' & '.join(bold(col) for col in header) + r' \\'))
            doc.append(NoEscape(r'\hline'))

            # Add table rows
            for _, row in df.iterrows():
                row_data = [
                    str(row['id']),
                    row['title'],
                    str(row['year']),
                    row['artists'],
                    row['format'],
                    row['location'],
                    NoEscape(r'\href{' + row['url'] + r'}{' + row['url'] + r'}')
                ]
                doc.append(NoEscape(' & '.join(row_data) + r' \\'))
                doc.append(NoEscape(r'\hline'))

            doc.append(NoEscape(r'\end{tabular}'))
    
    # Ensure the output directory exists. pylatex will attempt to open
    # '<output_file>.tex' for writing, so the directory must exist first.
    out_dir = os.path.dirname(output_file)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    doc.generate_pdf(output_file, clean_tex=False)

def sort_releases_by_artist(df: pd.DataFrame):
    '''
    Sort releases DataFrame by artist name, year and title, excluding various prefixes.
    '''
    def clean_artist_name(name: str) -> str:
        prefixes = ['The ', 'A ', 'An ', 'Le ', 'La ', 'Les ', 'El ', 'Los ', 'Das ', 'Der ', 'Die ']
        pattern = re.compile(r'^(?:' + '|'.join(prefixes) + r')', re.IGNORECASE)
        return pattern.sub('', name).strip()
    df['clean_artist'] = df['artists'].apply(clean_artist_name)
    df_sorted = df.sort_values(by=['clean_artist', 'year', 'title'])
    df_sorted = df_sorted.drop(columns=['clean_artist'])
    return df_sorted

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
    df_sorted = sort_releases_by_artist(df)
    
    # Make separate DataFrames for each location and generate PDFs
    locations = df_sorted['location'].unique()
    for loc in locations:
        df_loc = df_sorted[df_sorted['location'] == loc]
        output_file = f'output/collection_{loc.replace(" ", "_")}'
        generate_latex_pdf(df_loc, output_file)
        print(f"Generated PDF for location '{loc}': {output_file}.pdf")

if __name__ == '__main__':
    main()