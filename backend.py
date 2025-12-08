'''
backend.py

Backend logic for connecting to Discogs and fetching user collection data.
'''

import os
import sqlite3
import re
from contextlib import contextmanager
from dataclasses import dataclass

import discogs_client as dc
import yaml

CLIENT_NAME = 'FBM3334Client/0.2-SQLite'
REGEX_STRING = r'^\s*(?:the|a|el|la|los|las|un|una|le|la|les|un|une|il|lo|la|gli|le|ein|eine)\s+'

@dataclass
class PaginatedReleaseRequest:
    '''
    Paginated release request class.
    '''
    page: int = 0
    page_size: int = 10
    sort_by: str = 'artist'
    desc: bool = True
    search_query: str = ""
    artist_ids: list[int] | None = None
    genre_ids: list[int] | None = None
    style_ids: list[int] | None = None
    label_ids: list[int] | None = None
    formats: list[str] | None = None

class DiscogsManager:
    '''
    Wrapper class for Discogs API interactions and SQLite data management.
    '''

    def __init__(self):
        self.settings = {}
        self.pat = None
        self.client = None
        self.user = None
        self.load_settings()
        self.load_token()
        
        # Initialize DB
        self.init_db()

        self.progress_stage = ""

    def load_settings(self):
        '''
        Load settings from YAML file.
        '''
        try:
            with open('settings.yml', 'r', encoding='utf-8') as file:
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
        with open('settings.yml', 'w', encoding='utf-8') as file:
            yaml.dump(self.settings, file)

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
        self.client = dc.Client(CLIENT_NAME, user_token=self.pat)

    def identity(self):
        '''
        Fetch and return the user identity from Discogs.

        :return: Discogs user identity.
        '''
        if not self.client:
            raise ValueError("Client not connected.")
        self.user = self.client.identity()
        return self.user

    def get_db_path(self):
        '''
        Get the path to the SQLite database file.
        
        :return: Path to SQLite database file.
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
        with open('table_schema.txt', 'r', encoding='utf-8') as schema_file:
            schema = schema_file.read()
            with self.get_db_connection() as conn:
                conn.executescript(schema)
                conn.commit()

    # --- Data Ingestion ---
    def _insert_lookup(self, cursor, table, name_col, value):
        '''
        Helper to insert into lookup tables and return ID.

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

    def _save_release_to_release_db(self, basic_info: dict):
        '''
        Upserts the release into the main releases database.

        :param basic_info: Basic information dictionary from Discogs release
        :type basic_info: dict
        '''
        rel_id = basic_info.get('id')
        if not rel_id:
            return

        with self.get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                INSERT OR REPLACE INTO releases (id, master_id, title, year, thumb_url, release_url, format)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                rel_id,
                basic_info.get('master_id', 0),
                basic_info.get('title', ''),
                basic_info.get('year', ''),
                basic_info.get('thumb', ''),
                f"https://www.discogs.com/release/{rel_id}",
                basic_info.get('formats', {})[0].get('name', '')
            ))

            conn.commit()

    def _save_artist_to_artist_db(self, basic_info: dict):
        '''
        Sort the release into the relevant artist databases.

        :param basic_info: Basic information dictionary from Discogs release
        :type basic_info: dict
        '''
        rel_id = basic_info.get('id')
        if not rel_id:
            return

        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            # Clear old links for this release to prevent duplication on updates
            cursor.execute("DELETE FROM release_artists WHERE release_id = ?", (rel_id,))
            for i, artist in enumerate(basic_info.get('artists', [])):
                a_id = artist.get('id')
                a_name = artist.get('name')
                # Insert Artist if not exists
                cursor.execute("INSERT OR IGNORE INTO artists (id, name) VALUES (?, ?)", (a_id, a_name))
                cursor.execute(
                    "INSERT OR IGNORE INTO release_artists (release_id, artist_id, is_primary) VALUES (?, ?, ?)",
                    (rel_id, a_id, 1 if i == 0 else 0)
                )
            
            conn.commit()

    def _save_style_genre_label_to_dbs(self, basic_info: dict):
        '''
        Save the style, genre and label info into relevant databases.

        :param basic_info: Basic information dictionary from Discogs release
        :type basic_info: dict
        '''
        rel_id = basic_info.get('id')
        if not rel_id:
            return

        with self.get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("DELETE FROM release_genres WHERE release_id = ?", (rel_id,))
            for g in basic_info.get('genres', []):
                g_id = self._insert_lookup(cursor, 'genres', 'name', g)
                cursor.execute("INSERT INTO release_genres VALUES (?, ?)", (rel_id, g_id))

            cursor.execute("DELETE FROM release_styles WHERE release_id = ?", (rel_id,))
            for s in basic_info.get('styles', []):
                s_id = self._insert_lookup(cursor, 'styles', 'name', s)
                cursor.execute("INSERT INTO release_styles VALUES (?, ?)", (rel_id, s_id))

            cursor.execute("DELETE FROM release_labels WHERE release_id = ?", (rel_id,))
            for l in basic_info.get('labels', []):
                l_name = l.get('name')
                l_cat = l.get('catno')
                l_id = self._insert_lookup(cursor, 'labels', 'name', l_name)
                cursor.execute("INSERT INTO release_labels VALUES (?, ?, ?)", (rel_id, l_id, l_cat))

            conn.commit()

    def _save_custom_notes_to_dbs(self, basic_info: dict, notes: dict | None = None):
        '''
        Save the custom notes to the databases.

        :param basic_info: Basic information dictionary from Discogs release
        :type basic_info: dict
        :param notes: Optional custom notes associated with the release
        :type notes: dict | None
        '''
        rel_id = basic_info.get('id')
        if not rel_id:
            return
        
        # Firstly check the custom field IDs and create tables if necessary
        if notes is not None:
            for note in notes:
                field_id = note.get('field_id')
                # Create the table
                self.create_custom_field_db(field_id)

        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            if notes is not None:
                for note in notes:
                    field_id = note.get('field_id')                  
                    note = note.get('value', '').strip()
                    table_name = f'custom_field_{field_id}'
                    cursor.execute(f'''
                        INSERT OR REPLACE INTO {table_name} (release_id, field_value)
                        VALUES (?, ?)
                    ''', (rel_id, note))

            conn.commit()

    def save_release_to_db(self, basic_info: dict, notes: dict | None = None):
        '''
        Parses a single release dictionary and saves to normalised DB.

        :param basic_info: Basic information dictionary from Discogs release
        :type basic_info: dict
        :param notes: Optional custom notes associated with the release
        :type notes: dict | None
        '''

        self._save_release_to_release_db(basic_info)
        self._save_artist_to_artist_db(basic_info)
        self._save_style_genre_label_to_dbs(basic_info)
        self._save_custom_notes_to_dbs(basic_info, notes)

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
                    custom_field_ids.add(custom_field_id)
        return custom_field_ids
    
    def create_custom_field_db(self, field_id: int):
        '''
        Create a table for storing custom field values.

        :param field_id: ID of the custom field
        :type field_id: int
        '''
        table_name = f'custom_field_{field_id}'
        schema = f'''
        CREATE TABLE IF NOT EXISTS {table_name} (
            release_id INTEGER PRIMARY KEY,
            field_value TEXT,
            FOREIGN KEY(release_id) REFERENCES releases(id)
        );
        '''
        with self.get_db_connection() as conn:
            conn.executescript(schema)
            conn.commit()

    def fetch_collection(self, progress_callback=None):
        '''
        Fetches the collection from Discogs and updates the databases.
        :param progress_callback: Optional callback to report progress
        :type progress_callback: callable
        '''
        
        # API Download
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
                self.save_release_to_db(basic_info, item.notes)

            if item.notes:
                for note in item.notes:
                    custom_field_id = note['field_id']
                    custom_field_ids.add(custom_field_id)
            
            if progress_callback:
                progress_callback(i + 1, total_releases)
        
        print('Finished!')

    def _get_artists_missing_sort_name(self):
        '''
        Fetches artist IDs and names from the DB that lack a sort_name.
        '''
        with self.get_db_connection() as conn:
            # Assumes the connection/cursor supports dict-like access for rows
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT id, name FROM artists WHERE sort_name IS NULL")
            return cursor.fetchall()
        
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
        with self.get_db_connection() as sub_conn:
            res = sub_conn.execute(
                "SELECT release_id FROM release_artists WHERE artist_id = ? LIMIT 1", 
                (artist_id,)
            ).fetchone()
        
        if res:
            rel = self.client.release(res[0])
            rel.refresh() # Ensure full data
            return rel.data.get('artists_sort', default_name)
        else:
            return default_name
        
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
                self._commit_batch_updates(updates)
                updates = []
                
        # Commit remaining
        if updates:
            self._commit_batch_updates(updates)

    def _commit_batch_updates(self, updates_batch):
        '''
        Executes the database update for a given batch of (sort_name, id) tuples.

        :param updates_batch: Batch of tuples
        '''
        
        with self.get_db_connection() as conn:
            conn.executemany("UPDATE artists SET sort_name = ? WHERE id = ?", updates_batch)
            conn.commit()
        
    def _determine_sort_name(self, artist_id, artist_name):
        '''
        Determines the correct sort name, using simple check or API fetch.

        :param artist_id: Artist ID.
        :param artist_name: Artist name.
        '''
        
        thorough = self.settings.get('thorough_name_fetch', False)
        
        # 1. Simple Check (Fast Path)
        if not thorough and not self.check_artist_prefix(artist_name):
            return artist_name  # Sort name is the regular name
        
        # 2. API Fetch (Slow Path)
        try:
            return self._fetch_sort_name_from_api(artist_id, artist_name)
        except Exception as e:
            print(f"Error fetching sort name for {artist_name}: {e}")
            return artist_name # Fallback to regular name on error
    

    def fetch_artist_sort_names(self, progress_callback=None):
        '''
        Coordinates the fetching and updating of artist sort names.
        '''
                    
        artists_to_check = self._get_artists_missing_sort_name()
        if not artists_to_check:
            return
            
        if not self.client:
            self.connect_client()
            
        # 2. Processing and Batching
        self._process_and_batch_updates(artists_to_check, progress_callback)
        

    def check_artist_prefix(self, artist_name):
        '''
        Check the artist prefix against a regular expression,
        '''
        return re.match(REGEX_STRING, artist_name, re.IGNORECASE) is not None
    
    def clear_caches(self):
        db_path = self.get_db_path()
        if os.path.exists(db_path):
            os.remove(db_path)
            print("Database cleared.")

    def get_releases_paginated(self, request: PaginatedReleaseRequest):
        '''
        Coordinates fetching releases with full support for search, sorting, and pagination.

        :param page: The page number to retrieve (0-indexed).
        :type page: int
        :param page_size: The number of items per page.
        :type page_size: int
        :param sort_by: The column name to sort by ('title', 'year', 'date_added', 'id', 'artist').
        :type sort_by: str
        :param desc: If True, results are sorted in descending order; otherwise, ascending.
        :type desc: bool
        :param search_query: The text to search for across multiple release fields.
        :type search_query: str
        :returns: A tuple containing the list of release rows and the total count of matching releases.
        :rtype: tuple[list, int]
        '''
        # 1. Prepare SQL Components
        order_clause = self._build_order_clause(request.sort_by, request.desc)
        where_sql, search_params = self._build_where_clause(
            request.search_query,
            request.artist_ids,
            request.genre_ids,
            request.style_ids,
            request.label_ids,
            request.formats)

        # 2. Prepare Pagination
        offset = request.page * request.page_size

        with self.get_db_connection() as conn:
            # 3. Get Total Count
            total_rows = self._get_filtered_count(conn, where_sql, search_params)

            # 4. Handle 'Fetch All' and Finalize Pagination Params
            limit, final_offset = self._get_pagination_limits(
                request.page_size, total_rows, offset
                )
            full_params = search_params + [limit, final_offset]

            # 5. Fetch Data
            query = self._build_main_query(where_sql, order_clause)
            cursor = conn.execute(query, full_params)
            rows = [dict(row) for row in cursor.fetchall()]

        print(rows)

        return rows, total_rows

    def _build_order_clause(self, sort_by: str, desc: bool) -> str:
        '''
        Constructs the SQL ORDER BY clause with safe column selection.

        :param sort_by: The column name to sort by.
        :type sort_by: str
        :param desc: If True, sort descending; otherwise, ascending.
        :type desc: bool
        :returns: The complete SQL fragment for the ORDER BY clause.
        :rtype: str
        '''
        order_dir = 'DESC' if desc else 'ASC'
        allowed_sorts = ['title', 'year', 'date_added', 'id', 'artist']
        
        # Default to 'date_added' if input is invalid
        if sort_by not in allowed_sorts:
            sort_by = 'date_added'

        if sort_by == 'artist':
            # Use sort_name for artist sorting (collation is typically needed for SQLite text sorting)
            return f"COALESCE(a.sort_name, a.name) COLLATE NOCASE {order_dir}"
        else:
            return f"r.{sort_by} {order_dir}"

    def _build_where_clause(self, search_query: str, artist_ids: list[int] | None, genre_ids: list[int] | None, style_ids: list[int] | None, label_ids: list[int] | None, formats: list[str] | None) -> tuple[str, list]:
        '''
        Constructs the SQL WHERE clause and prepares search parameters, now including Genre, Style, and Label filters.
        '''
        conditions = []
        search_params = []
        
        # 1. General Search Query (UNCHANGED)
        if search_query:
            search_condition = '''
            (
                r.title LIKE ? OR
                r.year LIKE ? OR
                a.name LIKE ? OR
                l.name LIKE ? OR
                rl.catno LIKE ? OR
                s.name LIKE ?
            )
            '''
            conditions.append(search_condition)
            term = f"%{search_query}%"
            search_params.extend([term, term, term, term, term, term])
            
        # 2. Multiple Artist Filter (MODIFIED)
        if artist_ids:
            # Create a string of placeholders for the IN clause: '?, ?, ?'
            placeholders = ', '.join(['?'] * len(artist_ids))

            # Use 'a.id IN (...)' to filter by any of the selected artist IDs
            artist_condition = f'a.id IN ({placeholders})'
            conditions.append(artist_condition)
            
            # The list of artist_ids are the parameters for the IN clause
            search_params.extend(artist_ids)
            
        if genre_ids:
            placeholders = ', '.join(['?'] * len(genre_ids))
            
            # Use a subquery to find releases associated with the selected genres.
            # We use GROUP BY and COUNT to ensure the release matches ALL selected genres 
            # if that were the requirement, but typically it's OR logic (match ANY selected genre).
            # We use a simpler EXISTS/IN here for OR logic within the group.
            genre_condition = f"""
            r.id IN (
                SELECT release_id FROM release_genres 
                WHERE genre_id IN ({placeholders})
            )
            """
            conditions.append(genre_condition)
            search_params.extend(genre_ids)

        # 4. Multiple Style Filter (NEW)
        if style_ids:
            placeholders = ', '.join(['?'] * len(style_ids))
            style_condition = f"""
            r.id IN (
                SELECT release_id FROM release_styles 
                WHERE style_id IN ({placeholders})
            )
            """
            conditions.append(style_condition)
            search_params.extend(style_ids)

        # 5. Multiple Label Filter (NEW)
        if label_ids:
            placeholders = ', '.join(['?'] * len(label_ids))
            label_condition = f"""
            r.id IN (
                SELECT release_id FROM release_labels 
                WHERE label_id IN ({placeholders})
            )
            """
            conditions.append(label_condition)
            search_params.extend(label_ids)

        if formats:
            # The format is a column in the main 'releases' table
            placeholders = ', '.join(['?'] * len(formats))
            format_condition = f"r.format IN ({placeholders})"
            conditions.append(format_condition)
            search_params.extend(formats) # Pass the format strings as parameters
        
        if not conditions:
            return "", []

        # Combine all conditions with AND (AND logic between filter groups: Genre AND Style AND Label)
        where_sql = 'WHERE ' + ' AND '.join(conditions)
        
        return where_sql, search_params

    def _get_filtered_count(self, conn, where_sql: str, search_params: list) -> int:
        '''
        Executes the COUNT query to get the total number of rows matching the filter.

        :param conn: The active database connection object.
        :type conn: object
        :param where_sql: The WHERE SQL fragment, including 'WHERE' if present.
        :type where_sql: str
        :param search_params: The list of parameters for the search filter.
        :type search_params: list
        :returns: The total number of rows matching the criteria.
        :rtype: int
        '''
        count_query = f'''
        SELECT COUNT(DISTINCT r.id) 
        FROM releases r
        LEFT JOIN release_artists ra ON r.id = ra.release_id
        LEFT JOIN artists a ON ra.artist_id = a.id
        LEFT JOIN release_labels rl ON r.id = rl.release_id
        LEFT JOIN labels l ON rl.label_id = l.id
        LEFT JOIN release_genres gs on r.id = gs.release_id
        LEFT JOIN genres g on gs.genre_id = g.id
        LEFT JOIN release_styles rs on r.id = rs.release_id
        LEFT JOIN styles s on rs.style_id = s.id
        {where_sql}
        '''
        # Pass search_params to filter the count correctly
        return conn.execute(count_query, search_params).fetchone()[0]

    def _get_pagination_limits(self, page_size: int, total_rows: int, offset: int) -> tuple[int, int]:
        '''
        Calculates the final LIMIT and OFFSET values, handling the 'fetch all' case.

        :param page_size: The requested items per page.
        :type page_size: int
        :param total_rows: The total number of rows available.
        :type total_rows: int
        :param offset: The calculated starting offset.
        :type offset: int
        :returns: A tuple of (limit, offset) to use in the main query.
        :rtype: tuple[int, int]
        '''
        if page_size == 0:
            # Case: Fetch all releases
            return total_rows, 0
        else:
            return page_size, offset

    def _build_main_query(self, where_sql: str, order_clause: str) -> str:
        '''
        Constructs the main SQL query for fetching release data.

        :param where_sql: The WHERE SQL fragment, including 'WHERE' if present.
        :type where_sql: str
        :param order_clause: The complete SQL fragment for the ORDER BY clause.
        :type order_clause: str
        :returns: The full parameterized SQL query string.
        :rtype: str
        '''
        return f'''
        SELECT 
            r.id,
            REPLACE(GROUP_CONCAT(DISTINCT a.name), ',', ', ') as artist_name,
            r.title, 
            REPLACE(GROUP_CONCAT(DISTINCT l.name), ',', ', ') as label_name,
            REPLACE(GROUP_CONCAT(DISTINCT g.name), ',', ', ') as genres,
            REPLACE(GROUP_CONCAT(DISTINCT s.name), ',', ', ') as style_name,
            rl.catno, r.year, r.release_url, r.format, r.thumb_url
        FROM releases r
        LEFT JOIN release_artists ra ON r.id = ra.release_id
        LEFT JOIN artists a ON ra.artist_id = a.id
        LEFT JOIN release_labels rl ON r.id = rl.release_id
        LEFT JOIN release_genres gs on r.id = gs.release_id
        LEFT JOIN genres g on gs.genre_id = g.id
        LEFT JOIN labels l ON rl.label_id = l.id
        LEFT JOIN release_styles rs on r.id = rs.release_id
        LEFT JOIN styles s on rs.style_id = s.id
        {where_sql}
        GROUP BY r.id
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
        '''
    
    def get_all_artists(self):
        '''
        Fetches all unique artists from the DB, sorted by sort_name.
        
        :returns: List of dictionaries with 'id', 'name', and 'sort_name'.
        :rtype: list[dict]
        '''
        with self.get_db_connection() as conn:
            query = '''
            SELECT 
                id, 
                name, 
                COALESCE(sort_name, name) AS sort_name_for_order
            FROM artists
            ORDER BY sort_name_for_order COLLATE NOCASE ASC;
            '''
            cursor = conn.execute(query)
            # Use dict() to convert Row objects to dictionaries for easier consumption
            return [dict(row) for row in cursor.fetchall()]
        
    def get_artist_id_by_name(self, artist_name: str) -> int | None:
        '''
        Fetches the ID of an artist given their exact name.

        :param artist_name: The name of the artist to search for.
        :returns: The integer ID of the artist, or None if not found.
        :rtype: int | None
        '''
        with self.get_db_connection() as conn:
            query = '''
            SELECT
                id
            FROM artists
            WHERE name = ?;
            '''
            # Pass the artist_name as a tuple to the execute method.
            # This safely substitutes the '?' placeholder.
            cursor = conn.execute(query, (artist_name,))

            # Fetch the first (and only expected) result.
            # fetchone() returns a single Row object or None.
            row = cursor.fetchone()

            # Extract the 'id' from the row if it exists.
            return row['id'] if row else None
        
    def get_all_genres(self):
        '''
        Fetches all unique genres from the DB.
        
        :returns: List of dictionaries with 'id' and 'name'.
        :rtype: list[dict]
        '''
        with self.get_db_connection() as conn:
            query = '''
            SELECT 
                id, 
                name
            FROM genres
            ORDER BY id;
            '''
            cursor = conn.execute(query)
            # Use dict() to convert Row objects to dictionaries for easier consumption
            return [dict(row) for row in cursor.fetchall()]
        
    def get_genre_id_by_name(self,genre: str) -> int | None:
        '''
        Fetches the ID of a genre given its exact name.

        :param genre: The name of the genre to search for.
        :returns: The integer ID of the genre, or None if not found.
        :rtype: int | None
        '''
        with self.get_db_connection() as conn:
            query = '''
            SELECT
                id
            FROM genres
            WHERE name = ?;
            '''
            # Pass the artist_name as a tuple to the execute method.
            # This safely substitutes the '?' placeholder.
            cursor = conn.execute(query, (genre,))

            # Fetch the first (and only expected) result.
            # fetchone() returns a single Row object or None.
            row = cursor.fetchone()

            # Extract the 'id' from the row if it exists.
            return row['id'] if row else None
        
    def get_all_styles(self):
        '''
        Fetches all unique styles from the DB.
        
        :returns: List of dictionaries with 'id' and 'name'.
        :rtype: list[dict]
        '''
        with self.get_db_connection() as conn:
            query = '''
            SELECT 
                id, 
                name
            FROM styles
            ORDER BY name;
            '''
            cursor = conn.execute(query)
            # Use dict() to convert Row objects to dictionaries for easier consumption
            return [dict(row) for row in cursor.fetchall()]
        
    def get_style_id_by_name(self, style: str) -> int | None:
        '''
        Fetches the ID of a style given its exact name.

        :param style: The name of the style to search for.
        :returns: The integer ID of the style, or None if not found.
        :rtype: int | None
        '''
        with self.get_db_connection() as conn:
            query = '''
            SELECT
                id
            FROM styles
            WHERE name = ?;
            '''
            # Pass the artist_name as a tuple to the execute method.
            # This safely substitutes the '?' placeholder.
            cursor = conn.execute(query, (style,))

            # Fetch the first (and only expected) result.
            # fetchone() returns a single Row object or None.
            row = cursor.fetchone()

            # Extract the 'id' from the row if it exists.
            return row['id'] if row else None
        
    def get_all_labels(self):
        '''
        Fetches all unique labels from the DB.
        
        :returns: List of dictionaries with 'id' and 'name'.
        :rtype: list[dict]
        '''
        with self.get_db_connection() as conn:
            query = '''
            SELECT 
                id, 
                name
            FROM labels
            ORDER BY name;
            '''
            cursor = conn.execute(query)
            # Use dict() to convert Row objects to dictionaries for easier consumption
            return [dict(row) for row in cursor.fetchall()]
        
    def get_label_id_by_name(self, label: str) -> int | None:
        '''
        Fetches the ID of a style given its exact name.

        :param label: The name of the label to search for.
        :returns: The integer ID of the label, or None if not found.
        :rtype: int | None
        '''
        with self.get_db_connection() as conn:
            query = '''
            SELECT
                id
            FROM labels
            WHERE name = ?;
            '''
            # Pass the artist_name as a tuple to the execute method.
            # This safely substitutes the '?' placeholder.
            cursor = conn.execute(query, (label,))

            # Fetch the first (and only expected) result.
            # fetchone() returns a single Row object or None.
            row = cursor.fetchone()

            # Extract the 'id' from the row if it exists.
            return row['id'] if row else None
        
    def get_unique_formats(self) -> list[str]:
        '''
        Fetches all unique formats from the releases table in the DB.
        
        :returns: List of unique format strings.
        :rtype: list[str]
        '''
        with self.get_db_connection() as conn:
            query = '''
            SELECT DISTINCT
                format
            FROM releases
            WHERE format IS NOT NULL AND format != ''
            ORDER BY format ASC;
            '''
            cursor = conn.execute(query)
            # fetchall() returns a list of Row objects (which behave like tuples).
            # We use a list comprehension to extract the first (and only) column value (the format string).
            return [row[0] for row in cursor.fetchall()]
        
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