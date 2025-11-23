'''
backend.py

Backend logic for connecting to Discogs and fetching user collection data.
'''

import os
import time
import sqlite3
import json
import re
from contextlib import contextmanager

import pandas as pd
import discogs_client as dc
import yaml

CLIENT_NAME = 'FBM3334Client/0.2-SQLite'
REGEX_STRING = r'^\s*(?:the|a|el|la|los|las|un|una|le|la|les|un|une|il|lo|la|gli|le|ein|eine)\s+'

class DiscogsManager:
    '''
    Wrapper class for Discogs API interactions and SQLite data management.
    '''

    def __init__(self):
        self.settings = {}
        self.pat = None
        self.client = None
        self.user = None
        self.df = pd.DataFrame()
        self.load_settings()
        self.load_token()
        
        # Initialize DB
        self.init_db()

    def load_settings(self):
        '''
        Load settings from YAML file.
        '''
        try:
            with open('settings.yml', 'r') as file:
                self.settings = yaml.safe_load(file) or {}
        except FileNotFoundError:
            self.settings = {}

    def save_settings(self, new_settings):
        '''
        Save settings to YAML file.

        :param new_settings: dict of settings to update
        :type new_settings: dict
        '''
        self.settings.update(new_settings)
        with open('settings.yml', 'w') as file:
            yaml.dump(self.settings, file)

    def load_token(self):
        '''
        Load personal access token from secrets YAML file.
        '''
        try:
            with open('secrets.yml', 'r') as file:
                secrets = yaml.safe_load(file)
                self.pat = secrets.get('personal_access_token')
        except FileNotFoundError:
            self.pat = None

    def save_token(self, token):
        '''
        Save personal access token to secrets YAML file.
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
        Fetch and return the user identity from Discogs.
        '''
        if not self.client:
            raise ValueError("Client not connected.")
        self.user = self.client.identity()
        return self.user

    def get_db_path(self):
        '''
        Get the path to the SQLite database file.
        '''
        folder = self.settings.get('cache_folder', 'cache')
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, 'collection.db')

    @contextmanager
    def get_db_connection(self):
        '''
        Context manager for database connections.
        '''
        conn = sqlite3.connect(self.get_db_path())
        conn.row_factory = sqlite3.Row # Allows accessing columns by name
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self):
        '''
        Create normalised tables if they don't exist.
        '''
        schema = '''
        CREATE TABLE IF NOT EXISTS releases (
            id INTEGER PRIMARY KEY,
            master_id INTEGER,
            title TEXT,
            year TEXT,
            thumb_url TEXT,
            release_url TEXT,
            date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS artists (
            id INTEGER PRIMARY KEY,
            name TEXT,
            sort_name TEXT
        );

        CREATE TABLE IF NOT EXISTS genres (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        );

        CREATE TABLE IF NOT EXISTS styles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        );
        
        CREATE TABLE IF NOT EXISTS labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        );

        -- Junction Tables
        CREATE TABLE IF NOT EXISTS release_artists (
            release_id INTEGER,
            artist_id INTEGER,
            is_primary BOOLEAN DEFAULT 1,
            FOREIGN KEY(release_id) REFERENCES releases(id),
            FOREIGN KEY(artist_id) REFERENCES artists(id),
            PRIMARY KEY (release_id, artist_id)
        );

        CREATE TABLE IF NOT EXISTS release_genres (
            release_id INTEGER,
            genre_id INTEGER,
            FOREIGN KEY(release_id) REFERENCES releases(id),
            FOREIGN KEY(genre_id) REFERENCES genres(id)
        );

        CREATE TABLE IF NOT EXISTS release_styles (
            release_id INTEGER,
            style_id INTEGER,
            FOREIGN KEY(release_id) REFERENCES releases(id),
            FOREIGN KEY(style_id) REFERENCES styles(id)
        );
        
        CREATE TABLE IF NOT EXISTS release_labels (
            release_id INTEGER,
            label_id INTEGER,
            catno TEXT,
            FOREIGN KEY(release_id) REFERENCES releases(id),
            FOREIGN KEY(label_id) REFERENCES labels(id)
        );
        '''
        with self.get_db_connection() as conn:
            conn.executescript(schema)
            conn.commit()

    # --- Data Ingestion ---
    def _insert_lookup(self, cursor, table, name_col, value):
        '''
        Helper to insert into lookup tables (Genres, Styles, Labels) and return ID.

        :param cursor: SQLite cursor
        :param table: Table name
        :param name_col: Column name for the value
        :param value: Value to insert/look up
        :return: ID of the inserted or existing row
        '''
        if not value: return None
        
        # Try to find existing
        cursor.execute(f"SELECT id FROM {table} WHERE {name_col} = ?", (value,))
        res = cursor.fetchone()
        if res:
            return res['id']
        
        # Insert new
        cursor.execute(f"INSERT INTO {table} ({name_col}) VALUES (?)", (value,))
        return cursor.lastrowid

    def save_release_to_db(self, basic_info: dict):
        '''
        Parses a single release dictionary and saves to normalised DB.

        :param basic_info: Basic information dictionary from Discogs release
        :type basic_info: dict
        '''
        rel_id = basic_info.get('id')
        if not rel_id: return

        with self.get_db_connection() as conn:
            cursor = conn.cursor()

            # 1. Upsert Release
            cursor.execute('''
                INSERT OR REPLACE INTO releases (id, master_id, title, year, thumb_url, release_url)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                rel_id,
                basic_info.get('master_id', 0),
                basic_info.get('title', ''),
                basic_info.get('year', ''),
                basic_info.get('thumb', ''),
                f"https://www.discogs.com/release/{rel_id}"
            ))

            # 2. Handle Artists
            # Clear old links for this release to prevent duplication on updates
            cursor.execute("DELETE FROM release_artists WHERE release_id = ?", (rel_id,))
            
            for i, artist in enumerate(basic_info.get('artists', [])):
                a_id = artist.get('id')
                a_name = artist.get('name')
                
                # Insert Artist if not exists
                cursor.execute("INSERT OR IGNORE INTO artists (id, name) VALUES (?, ?)", (a_id, a_name))
                
                # Link - CHANGED THIS LINE TO "INSERT OR IGNORE"
                cursor.execute("INSERT OR IGNORE INTO release_artists (release_id, artist_id, is_primary) VALUES (?, ?, ?)",
                               (rel_id, a_id, 1 if i == 0 else 0))

            # 3. Handle Genres
            cursor.execute("DELETE FROM release_genres WHERE release_id = ?", (rel_id,))
            for g in basic_info.get('genres', []):
                g_id = self._insert_lookup(cursor, 'genres', 'name', g)
                cursor.execute("INSERT INTO release_genres VALUES (?, ?)", (rel_id, g_id))

            # 4. Handle Styles
            cursor.execute("DELETE FROM release_styles WHERE release_id = ?", (rel_id,))
            for s in basic_info.get('styles', []):
                s_id = self._insert_lookup(cursor, 'styles', 'name', s)
                cursor.execute("INSERT INTO release_styles VALUES (?, ?)", (rel_id, s_id))

            # 5. Handle Labels
            cursor.execute("DELETE FROM release_labels WHERE release_id = ?", (rel_id,))
            for l in basic_info.get('labels', []):
                l_name = l.get('name')
                l_cat = l.get('catno')
                l_id = self._insert_lookup(cursor, 'labels', 'name', l_name)
                cursor.execute("INSERT INTO release_labels VALUES (?, ?, ?)", (rel_id, l_id, l_cat))

            conn.commit()

    def fetch_collection(self, force_update=False, progress_callback=None):
        '''
        Logic:
        1. If not force_update, try loading from DB.
        2. If DB empty or force_update, fetch from API -> Save to DB -> Load from DB.

        :param force_update: Whether to force API fetch
        :type force_update: bool
        :param progress_callback: Optional callback to report progress
        :type progress_callback: callable
        :return: DataFrame of collection
        :rtype: pd.DataFrame
        '''
        
        # Attempt to load existing data first
        if not force_update:
            self.df = self.load_df_from_db()
            if not self.df.empty:
                # Check update interval (optional logic here)
                print("Loaded collection from Database.")
                return self.df

        # API Download
        if not self.client: self.connect_client()
        if not self.user: self.identity()

        print("Fetching from Discogs API...")
        releases_to_process = self.user.collection_folders[0].releases
        total_releases = len(releases_to_process)

        for i, item in enumerate(releases_to_process):
            # item.data['basic_information'] contains exactly what we need
            # We don't need self.client.release() usually, unless we need extra deep data
            basic_info = item.data.get('basic_information')
            if basic_info:
                self.save_release_to_db(basic_info)
            
            if progress_callback:
                progress_callback(i + 1, total_releases)
        
        # Reload DF from the newly populated DB
        self.df = self.load_df_from_db()
        return self.df

    def load_df_from_db(self):
        '''
        Reconstructs the flat DataFrame from the normalized SQLite tables.
        This simulates your old JSON structure for compatibility with the rest of your app.
        '''
        query = '''
        SELECT 
            r.id, r.master_id, r.title, r.release_year, r.thumb_url as image_url, r.release_url as url,
            
            -- Aggregate Artists
            GROUP_CONCAT(DISTINCT a.name) as artists,
            a_first.id as first_artist_id,
            
            -- We will fetch lists for genres/styles/labels in a post-process or subquery
            -- Doing complex JSON aggregation in SQLite is possible but verbose.
            -- For simplicity, we fetch core data and lists separately, or use Python to aggregate.
            
            r.year
        FROM releases r
        LEFT JOIN release_artists ra ON r.id = ra.release_id AND ra.is_primary = 1
        LEFT JOIN artists a_first ON ra.artist_id = a_first.id
        LEFT JOIN release_artists ra_all ON r.id = ra_all.release_id
        LEFT JOIN artists a ON ra_all.artist_id = a.id
        GROUP BY r.id
        '''
        
        # It is actually cleaner to read tables and merge in Pandas to ensure 
        # we get actual Python Lists, not comma-separated strings.
        
        with self.get_db_connection() as conn:
            df_releases = pd.read_sql("SELECT * FROM releases", conn)
            if df_releases.empty: return pd.DataFrame()

            # Helper to fetch lookup map
            def get_lookup_map(query, id_col, val_col):
                sub_df = pd.read_sql(query, conn)
                return sub_df.groupby(id_col)[val_col].apply(list).to_dict()

            # 1. Genres
            genre_map = get_lookup_map('''
                SELECT rg.release_id, g.name 
                FROM release_genres rg JOIN genres g ON rg.genre_id = g.id
            ''', 'release_id', 'name')

            # 2. Styles
            style_map = get_lookup_map('''
                SELECT rs.release_id, s.name 
                FROM release_styles rs JOIN styles s ON rs.style_id = s.id
            ''', 'release_id', 'name')
            
            # 3. Artists (List)
            artist_map = get_lookup_map('''
                SELECT ra.release_id, a.name 
                FROM release_artists ra JOIN artists a ON ra.artist_id = a.id
            ''', 'release_id', 'name')

            # 4. Labels & CatNos
            label_df = pd.read_sql('''
                SELECT rl.release_id, l.name, rl.catno 
                FROM release_labels rl JOIN labels l ON rl.label_id = l.id
            ''', conn)
            label_map = label_df.groupby('release_id')['name'].apply(list).to_dict()
            catno_map = label_df.groupby('release_id')['catno'].apply(list).to_dict()

            # 5. First Artist ID (for sorting)
            first_artist_df = pd.read_sql('''
                SELECT release_id, artist_id FROM release_artists WHERE is_primary = 1
            ''', conn)
            first_artist_map = first_artist_df.set_index('release_id')['artist_id'].to_dict()

        # Map data back to DataFrame
        df_releases['genre_list'] = df_releases['id'].map(genre_map).apply(lambda x: x if isinstance(x, list) else [])
        df_releases['style_list'] = df_releases['id'].map(style_map).apply(lambda x: x if isinstance(x, list) else [])
        df_releases['artist_list'] = df_releases['id'].map(artist_map).apply(lambda x: x if isinstance(x, list) else [])
        df_releases['label_list'] = df_releases['id'].map(label_map).apply(lambda x: x if isinstance(x, list) else [])
        df_releases['catno_list'] = df_releases['id'].map(catno_map).apply(lambda x: x if isinstance(x, list) else [])
        df_releases['first_artist_id'] = df_releases['id'].map(first_artist_map)
        
        # Create string representation for display
        df_releases['artists'] = df_releases['artist_list'].apply(lambda x: ', '.join(x))

        # Retrieve cached sort names
        with self.get_db_connection() as conn:
             artist_sort_df = pd.read_sql("SELECT id, sort_name FROM artists WHERE sort_name IS NOT NULL", conn)
             sort_map = artist_sort_df.set_index('id')['sort_name'].to_dict()
             df_releases['artist_sort_name'] = df_releases['first_artist_id'].map(sort_map).fillna('')

        return df_releases

    # --- Artist Sort Name Logic ---
    def fetch_artist_sort_names(self, progress_callback=None):
        '''
        Updates the 'artists' table with sort_names where missing.
        '''
        if self.df.empty: self.fetch_collection()
        
        # Find artists in DB that don't have a sort_name
        with self.get_db_connection() as conn:
            # Get unique artist IDs from our collection that lack sort names
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT id, name FROM artists WHERE sort_name IS NULL")
            artists_to_check = cursor.fetchall()
        
        total = len(artists_to_check)
        thorough = self.settings.get('thorough_name_fetch', False)
        
        if not self.client: self.connect_client()

        updates = [] # Store tuples (sort_name, id)

        for i, row in enumerate(artists_to_check):
            a_id, a_name = row['id'], row['name']
            
            # 1. Simple check (Prefixes)
            if not thorough and not self.check_artist_prefix(a_name):
                updates.append((a_name, a_id))
            
            # 2. API Fetch
            else:
                try:
                    # Fetch artist details from API
                    # Note: Discogs API rate limits apply; this can be slow
                    artist_obj = self.client.artist(a_id)
                    
                    with self.get_db_connection() as sub_conn:
                        res = sub_conn.execute("SELECT release_id FROM release_artists WHERE artist_id = ? LIMIT 1", (a_id,)).fetchone()
                        if res:
                            rel = self.client.release(res[0])
                            rel.refresh() # Ensure full data
                            sort_name = rel.data.get('artists_sort', a_name)
                            print(sort_name)
                            updates.append((sort_name, a_id))
                        else:
                            updates.append((a_name, a_id))
                            
                except Exception as e:
                    print(f"Error fetching sort name for {a_name}: {e}")
                    updates.append((a_name, a_id))

            if progress_callback:
                progress_callback(i + 1, total)
                
            # Batch update every 10 or at end
            if len(updates) >= 10:
                with self.get_db_connection() as conn:
                    conn.executemany("UPDATE artists SET sort_name = ? WHERE id = ?", updates)
                    conn.commit()
                updates = []
        
        # Commit remaining
        if updates:
            with self.get_db_connection() as conn:
                conn.executemany("UPDATE artists SET sort_name = ? WHERE id = ?", updates)
                conn.commit()
        
        # Refresh the dataframe
        return self.load_df_from_db()

    def check_artist_prefix(self, artist_name):
        return re.match(REGEX_STRING, artist_name, re.IGNORECASE) is not None
    
    def clear_caches(self):
        db_path = self.get_db_path()
        if os.path.exists(db_path):
            os.remove(db_path)
            print("Database cleared.")

    def get_releases_paginated(self, page: int = 0, page_size: int = 10, sort_by: str = 'date_added', desc: bool = True, search_query: str = None):
        '''
        Fetches data with support for Search, Sorting, and Pagination.
        '''
        offset = page * page_size
        order_dir = 'DESC' if desc else 'ASC'
        
        # 1. Safe Sort Column Selection
        allowed_sorts = ['title', 'year', 'date_added', 'id', 'artist']
        if sort_by not in allowed_sorts: sort_by = 'date_added'

        if sort_by == 'artist':
            order_clause = f"COALESCE(a.sort_name, a.name) COLLATE NOCASE {order_dir}"
        else:
            order_clause = f"r.{sort_by} {order_dir}"

        # 2. Construct the WHERE clause dynamically
        where_sql = ""
        search_params = []
        
        if search_query:
            # We verify title, artist name, label name, year, and catalog number
            where_sql = '''
            WHERE (
                r.title LIKE ? OR
                r.year LIKE ? OR
                a.name LIKE ? OR
                l.name LIKE ? OR
                rl.catno LIKE ?
            )
            '''
            # We need to pass the search term for EACH '?' placeholder
            term = f"%{search_query}%"
            search_params = [term, term, term, term, term]

        # 3. Main Query
        # Note: We removed "ra.is_primary = 1" from the JOIN for the search context 
        # so we can find releases even if the searched artist is a "feat." or remixer.
        # However, for display consistency in the SELECT, we might still prefer the primary.
        # For a generic search, checking ALL joined artists is better.
        
        query = f'''
        SELECT 
            r.id, r.title, r.year, r.thumb_url, 
            -- Use MAX/Group Concat to grab a representative artist/label if multiple exist due to the join
            GROUP_CONCAT(DISTINCT a.name) as artist_name,
            GROUP_CONCAT(DISTINCT l.name) as label_name,
            rl.catno
        FROM releases r
        LEFT JOIN release_artists ra ON r.id = ra.release_id
        LEFT JOIN artists a ON ra.artist_id = a.id
        LEFT JOIN release_labels rl ON r.id = rl.release_id
        LEFT JOIN labels l ON rl.label_id = l.id
        {where_sql}
        GROUP BY r.id
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
        '''
        
        # 4. Count Query (Must also respect the search filter!)
        count_query = f'''
        SELECT COUNT(DISTINCT r.id) 
        FROM releases r
        LEFT JOIN release_artists ra ON r.id = ra.release_id
        LEFT JOIN artists a ON ra.artist_id = a.id
        LEFT JOIN release_labels rl ON r.id = rl.release_id
        LEFT JOIN labels l ON rl.label_id = l.id
        {where_sql}
        '''

        with self.get_db_connection() as conn:
            # Execute Count
            # search_params is passed here to filter the count correctly
            total_rows = conn.execute(count_query, search_params).fetchone()[0]
            
            # Execute Data Fetch
            # Combine search_params with pagination params (limit, offset)
            full_params = search_params + [page_size, offset]
            cursor = conn.execute(query, full_params)
            rows = [dict(row) for row in cursor.fetchall()]
            
        return rows, total_rows