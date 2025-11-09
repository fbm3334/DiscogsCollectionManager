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


