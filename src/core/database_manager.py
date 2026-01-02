import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
import logging
from typing import Dict, List

from core.core_classes import PaginatedReleaseRequest


class DatabaseManager:
    """
    Database manager class for maintaining and getting data from the SQLite
    database.
    """
    # Core directory location.
    CORE_DIR = Path(__file__).resolve().parent
    BASE_DIR = CORE_DIR.parent.parent
    CACHE_FOLDER = BASE_DIR / "cache"
    BLANKS_LABEL = "[Blanks]"

    def __init__(self):
        """
        Class initialisation function
        """
        self.custom_ids = set()
        # Ensure the database and tables exist immediately
        self.init_db()
        # Load any existing custom field tables into memory
        self._load_custom_field_ids_from_db()
        logging.debug("Full database initialisation done.")

    def get_db_path(self):
        """
        Get the path to the SQLite database file.

        :return: Path to SQLite database file.
        """
        self.CACHE_FOLDER.mkdir(parents=True, exist_ok=True)
        return self.CACHE_FOLDER / "collection.db"

    @contextmanager
    def get_db_connection(self):
        """
        Context manager for database connections.
        """
        conn = sqlite3.connect(self.get_db_path())
        conn.row_factory = sqlite3.Row  # Allows accessing columns by name
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self):
        """
        Initialise the database by creating normalised tables if they don't
        exist.
        """
        schema_path = self.CORE_DIR / "table_schema.txt"

        if not schema_path.exists():
            raise FileNotFoundError(f"Schema not found at {schema_path}")

        schema = schema_path.read_text(encoding="utf-8")
        
        with self.get_db_connection() as conn:
            conn.executescript(schema)
            conn.commit()
        logging.debug('Database tables created.')

    def _insert_lookup(self, cursor, table, name_col, value):
        """
        Helper to insert a value into lookup tables and return ID.

        :param cursor: SQLite cursor
        :param table: Table name
        :param name_col: Column name for the value
        :param value: Value to insert/look up
        :return: ID of the inserted or existing row
        """
        if not value:
            return None

        # Try to find existing
        cursor.execute(f"SELECT id FROM {table} WHERE {name_col} = ?", (value,))
        res = cursor.fetchone()
        if res:
            return res["id"]

        # Insert new
        cursor.execute(f"INSERT INTO {table} ({name_col}) VALUES (?)", (value,))
        return cursor.lastrowid

    def _save_release_to_release_db(self, conn, basic_info: dict):
        """
        Upserts the release into the main releases database.

        :param conn: Database connection
        :param basic_info: Basic information dictionary from Discogs release
        :type basic_info: dict
        """
        rel_id = basic_info.get("id")
        if not rel_id:
            return

        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO releases (id, master_id, title, year, thumb_url, release_url, format)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                rel_id,
                basic_info.get("master_id", 0),
                basic_info.get("title", ""),
                basic_info.get("year", ""),
                basic_info.get("thumb", ""),
                f"https://www.discogs.com/release/{rel_id}",
                basic_info.get("formats", {})[0].get("name", ""),
            ),
        )

        conn.commit()

    def _load_custom_field_ids_from_db(self):
        """
        Loads all known custom field IDs by querying the SQLite master table.
        This ensures custom fields are available even if fetch_collection isn't run.
        """
        self.custom_ids = set()

        # Query the SQLite master table to find all tables matching the pattern
        query = "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'custom_field_%';"

        with self.get_db_connection() as conn:
            cursor = conn.execute(query)
            for row in cursor.fetchall():
                table_name = row["name"]
                # Extract the ID from the table name (e.g., 'custom_field_1' -> '1')
                try:
                    field_id = int(table_name.replace("custom_field_", ""))
                    self.custom_ids.add(field_id)
                except ValueError:
                    # Ignore tables that don't follow the naming convention
                    continue

    def get_custom_field_ids_set(self) -> set:
        """
        Get the custom field IDs from the database.

        :return: Set containing custom field IDs.
        :rtype: set
        """
        return self.custom_ids

    def _save_artist_to_artist_db(self, conn, basic_info: dict):
        """
        Sort the release into the relevant artist databases.

        :param conn: Database connection
        :param basic_info: Basic information dictionary from Discogs release
        :type basic_info: dict
        """
        rel_id = basic_info.get("id")
        if not rel_id:
            return

        cursor = conn.cursor()
        # Clear old links for this release to prevent duplication on updates
        cursor.execute("DELETE FROM release_artists WHERE release_id = ?", (rel_id,))
        for i, artist in enumerate(basic_info.get("artists", [])):
            a_id = artist.get("id")
            a_name = artist.get("name")
            # Insert Artist if not exists
            cursor.execute(
                "INSERT OR IGNORE INTO artists (id, name) VALUES (?, ?)", (a_id, a_name)
            )
            cursor.execute(
                "INSERT OR IGNORE INTO release_artists (release_id, artist_id, is_primary) VALUES (?, ?, ?)",
                (rel_id, a_id, 1 if i == 0 else 0),
            )

        conn.commit()

    def _save_style_genre_label_to_dbs(self, conn, basic_info: dict):
        """
        Save the style, genre and label info into relevant databases.

        :param conn: Database connection
        :param basic_info: Basic information dictionary from Discogs release
        :type basic_info: dict
        """
        rel_id = basic_info.get("id")
        if not rel_id:
            return

        cursor = conn.cursor()

        cursor.execute("DELETE FROM release_genres WHERE release_id = ?", (rel_id,))
        for genre in basic_info.get("genres", []):
            g_id = self._insert_lookup(cursor, "genres", "name", genre)
            cursor.execute("INSERT INTO release_genres VALUES (?, ?)", (rel_id, g_id))

        cursor.execute("DELETE FROM release_styles WHERE release_id = ?", (rel_id,))
        for s in basic_info.get("styles", []):
            s_id = self._insert_lookup(cursor, "styles", "name", s)
            cursor.execute("INSERT INTO release_styles VALUES (?, ?)", (rel_id, s_id))

        cursor.execute("DELETE FROM release_labels WHERE release_id = ?", (rel_id,))
        for label in basic_info.get("labels", []):
            l_name = label.get("name")
            l_cat = label.get("catno")
            l_id = self._insert_lookup(cursor, "labels", "name", l_name)
            cursor.execute(
                "INSERT INTO release_labels VALUES (?, ?, ?)", (rel_id, l_id, l_cat)
            )

        conn.commit()

    def _save_custom_notes_to_dbs(
        self, conn, basic_info: dict, notes: dict | None = None
    ):
        """
        Save the custom notes to the databases.

        :param conn: Database connection
        :param basic_info: Basic information dictionary from Discogs release
        :type basic_info: dict
        :param notes: Optional custom notes associated with the release
        :type notes: dict | None
        """
        rel_id = basic_info.get("id")
        if not rel_id:
            return

        # Firstly check the custom field IDs and create tables if necessary
        if notes is not None:
            for note in notes:
                field_id = note.get("field_id")
                # Create the table
                self.create_custom_field_db(conn, field_id)
                logging.debug(f"Creating custom field ID {field_id}")

        cursor = conn.cursor()
        if notes is not None:
            for note in notes:
                field_id = note.get("field_id")
                note = note.get("value", "").strip()
                table_name = f"custom_field_{field_id}"
                cursor.execute(
                    f"""
                    INSERT OR REPLACE INTO {table_name} (release_id, field_value)
                    VALUES (?, ?)
                """,
                    (rel_id, note),
                )

        conn.commit()

    def save_release_to_db(self, conn, basic_info: dict, notes: dict | None = None):
        """
        Parses a single release dictionary and saves to normalised DB.

        :param conn: Database connection.
        :param basic_info: Basic information dictionary from Discogs release
        :type basic_info: dict
        :param notes: Optional custom notes associated with the release
        :type notes: dict | None
        """

        self._save_release_to_release_db(conn, basic_info)
        self._save_artist_to_artist_db(conn, basic_info)
        self._save_style_genre_label_to_dbs(conn, basic_info)
        self._save_custom_notes_to_dbs(conn, basic_info, notes)

    def create_custom_field_db(self, conn, field_id: int):
        """
        Create a table for storing custom field values.

        :param conn: Database connection
        :param field_id: ID of the custom field
        :type field_id: int
        """
        table_name = f"custom_field_{field_id}"
        schema = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            release_id INTEGER PRIMARY KEY,
            field_value TEXT,
            FOREIGN KEY(release_id) REFERENCES releases(id)
        );
        """
        conn.executescript(schema)
        conn.commit()

    def add_releases_to_db(self, release_list: list):
        """
        Add a list of releases fetched from Discogs to the database.

        :param release_list: List of releases to add.
        :type release_list: list
        """
        with self.get_db_connection() as conn:
            for basic_info, notes in release_list:
                self.save_release_to_db(conn, basic_info, notes)

    def get_artists_missing_sort_name(self):
        """
        Fetches artist IDs and names from the DB that lack a sort_name.

        :param conn: Database connection.
        :return: List of artists missing a sort name.
        :rtype: list
        """
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT DISTINCT id, name FROM artists WHERE sort_name IS NULL"
            )
            return cursor.fetchall()

    def get_first_release_from_artist(self, artist_id):
        """
        Get the first release with the matching artist ID.
        """
        with self.get_db_connection() as conn:
            return conn.execute(
                "SELECT release_id FROM release_artists WHERE artist_id = ? LIMIT 1",
                (artist_id,),
            ).fetchone()

    def commit_batch_updates(self, updates_batch):
        """
        Executes the database update for a given batch of (sort_name, id) tuples.

        :param updates_batch: Batch of tuples
        """
        with self.get_db_connection() as conn:
            conn.executemany(
                "UPDATE artists SET sort_name = ? WHERE id = ?", updates_batch
            )
            conn.commit()

    def delete_database(self):
        """
        Delete the database.
        """
        db_path = self.get_db_path()
        if os.path.exists(db_path):
            os.remove(db_path)

    def _build_order_clause(self, sort_by: str, desc: bool) -> str:
        """
        Constructs the SQL ORDER BY clause with safe column selection.

        :param sort_by: The column name to sort by.
        :type sort_by: str
        :param desc: If True, sort descending; otherwise, ascending.
        :type desc: bool
        :returns: The complete SQL fragment for the ORDER BY clause.
        :rtype: str
        """

        order_dir = "DESC" if desc else "ASC"

        # Check if the sort is by a custom field
        if sort_by.startswith("custom_") and sort_by.replace("custom_", "").isdigit():
            return f"{sort_by} COLLATE NOCASE {order_dir}"

        allowed_sorts = ["title", "year", "date_added", "id", "artist"]

        # Default to 'date_added' if input is invalid
        if sort_by not in allowed_sorts:
            sort_by = "date_added"

        if sort_by == "artist":
            # Use sort_name for artist sorting (collation is typically needed for SQLite text sorting)
            return f"COALESCE(a.sort_name, a.name) COLLATE NOCASE {order_dir}"
        else:
            return f"r.{sort_by} {order_dir}"

    def _build_in_condition(
        self,
        column: str,
        values: list[int] | list[str] | None,
        conditions: list,
        params: list,
    ) -> None:
        """
        Helper for simple filters like Artist ID or Format, using IN (?).

        :param column: The fully qualified SQL column name (e.g., 'a.id' or 'r.format').
        :type column: str
        :param values: A list of values (e.g., IDs or strings) to be included in the IN clause.
                       If the list is empty or None, no condition is added.
        :type values: list
        :param conditions: The main list of SQL WHERE condition strings to append to.
        :type conditions: list
        :param params: The main list of query parameters to append the filter values to.
        :type params: list
        :rtype: None
        """
        if values:
            placeholders = ", ".join(["?"] * len(values))
            condition = f"{column} IN ({placeholders})"
            conditions.append(condition)
            params.extend(values)

    def _build_subquery_in_condition(
        self,
        table: str,
        column: str,
        ids: list[int] | None,
        conditions: list,
        params: list,
    ) -> None:
        """
        Helper for many-to-many filters (Genre, Style, Label) using subqueries.

        This is necessary because these filters rely on junction tables (e.g., release_genres).
        It implements OR logic: find releases associated with ANY of the provided IDs.

        :param table: The name of the junction table (e.g., 'release_genres').
        :type table: str
        :param column: The name of the ID column within the junction table (e.g., 'genre_id').
        :type column: str
        :param ids: A list of primary keys (IDs) to filter by.
        :type ids: list[int]
        :param conditions: The main list of SQL WHERE condition strings to append to.
        :type conditions: list
        :param params: The main list of query parameters to append the filter IDs to.
        :type params: list
        :rtype: None
        """
        if ids:
            placeholders = ", ".join(["?"] * len(ids))
            condition = f"""
            r.id IN (
                SELECT release_id FROM {table} 
                WHERE {column} IN ({placeholders})
            )
            """
            conditions.append(condition)
            params.extend(ids)

    def _handle_custom_field_filter(
        self, field_id: int, values: list[str], conditions: list, params: list
    ) -> None:
        """
        Handles the complex logic for a single custom field filter, including special
        handling for the '[Blanks]' option.

        This method generates a combined condition using OR logic: (Blanks OR Value1 OR Value2).
        It assumes the main query has already LEFT JOINed the necessary custom field table
        using the alias 'cf{field_id}'.

        :param field_id: The ID of the custom field being filtered.
        :type field_id: int
        :param values: A list of desired field values, which may include the special
                       '[Blanks]' constant.
        :type values: list[str]
        :param conditions: The main list of SQL WHERE condition strings to append to.
        :type conditions: list
        :param params: The main list of query parameters to append the specific field values to.
        :type params: list
        :rtype: None
        """
        # Implementation remains the same:
        if not values:
            return

        alias = f"cf{field_id}"

        filtered_values = [v for v in values if v != self.BLANKS_LABEL]
        is_blanks_selected = self.BLANKS_LABEL in values

        combined_condition = []

        # A. Blanks Condition
        if is_blanks_selected:
            # Matches releases where the field is missing (NULL join) or the value is empty/null.
            blanks_condition = f"({alias}.release_id IS NULL OR {alias}.field_value IS NULL OR TRIM({alias}.field_value) = '')"
            combined_condition.append(blanks_condition)

        # B. Specific Value Condition
        if filtered_values:
            placeholders = ", ".join(["?"] * len(filtered_values))
            value_condition = f"{alias}.field_value IN ({placeholders})"
            combined_condition.append(value_condition)
            params.extend(filtered_values)

        # C. Combine Conditions (OR logic)
        if combined_condition:
            custom_field_condition = f"({' OR '.join(combined_condition)})"
            conditions.append(custom_field_condition)

    def _build_where_clause(
        self,
        search_query: str,
        artist_ids: list[int] | None,
        genre_ids: list[int] | None,
        style_ids: list[int] | None,
        label_ids: list[int] | None,
        formats: list[str] | None,
        custom_field_filters: dict[int, list[str]] | None,
    ) -> tuple[str, list]:
        """
        Constructs the SQL WHERE clause and prepares search parameters, now including Genre, Style, and Label filters.
        """
        conditions = []
        search_params = []

        # 1. General Search Query
        if search_query:
            search_condition = """
            (
                r.title LIKE ? OR r.year LIKE ? OR a.name LIKE ? OR 
                l.name LIKE ? OR rl.catno LIKE ? OR s.name LIKE ?
            )
            """
            conditions.append(search_condition)
            term = f"%{search_query}%"
            search_params.extend([term] * 6)

        # 2. Artist Filter (Simple IN condition)
        self._build_in_condition(
            column="a.id",
            values=artist_ids,
            conditions=conditions,
            params=search_params,
        )

        # 3. Genre Filter (Subquery IN condition)
        self._build_subquery_in_condition(
            table="release_genres",
            column="genre_id",
            ids=genre_ids,
            conditions=conditions,
            params=search_params,
        )

        # 4. Style Filter (Subquery IN condition)
        self._build_subquery_in_condition(
            table="release_styles",
            column="style_id",
            ids=style_ids,
            conditions=conditions,
            params=search_params,
        )

        # 5. Label Filter (Subquery IN condition)
        self._build_subquery_in_condition(
            table="release_labels",
            column="label_id",
            ids=label_ids,
            conditions=conditions,
            params=search_params,
        )

        # 6. Format Filter (Simple IN condition)
        self._build_in_condition(
            column="r.format",
            values=formats,
            conditions=conditions,
            params=search_params,
        )

        # 7. Custom Field Filters
        if custom_field_filters:
            for field_id, values in custom_field_filters.items():
                self._handle_custom_field_filter(
                    field_id=field_id,
                    values=values,
                    conditions=conditions,
                    params=search_params,
                )

        # Final Assembly
        if not conditions:
            return "", []

        # Combine all conditions with AND
        where_sql = "WHERE " + " AND ".join(conditions)

        return where_sql, search_params

    def _build_custom_field_joins(self) -> tuple[str, str]:
        """
        Builds the SELECT and JOIN clauses for all known custom fields.

        :returns: A tuple (custom_select_sql, custom_join_sql)
        :rtype: tuple[str, str]
        """
        custom_select_parts = []
        custom_join_parts = []

        for field_id in self.custom_ids:
            table_name = f"custom_field_{field_id}"
            alias = f"cf{field_id}"

            # SELECT part is only needed for the main query
            custom_select_parts.append(f"{alias}.field_value AS custom_{field_id}")

            # JOIN part is needed for both count and main queries
            custom_join_parts.append(f"""
                LEFT JOIN {table_name} {alias} ON r.id = {alias}.release_id
            """)

        custom_select_sql = (
            ",\n" + ",\n".join(custom_select_parts) if custom_select_parts else ""
        )
        custom_join_sql = "\n".join(custom_join_parts)

        return custom_select_sql, custom_join_sql

    def _get_filtered_count(self, conn, where_sql: str, search_params: list) -> int:
        """
        Executes the COUNT query to get the total number of rows matching the filter.

        :param conn: The active database connection object.
        :type conn: object
        :param where_sql: The WHERE SQL fragment, including 'WHERE' if present.
        :type where_sql: str
        :param search_params: The list of parameters for the search filter.
        :type search_params: list
        :returns: The total number of rows matching the criteria.
        :rtype: int
        """
        # Get the required custom field joins
        _, custom_join_sql = self._build_custom_field_joins()

        count_query = f"""
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
        {custom_join_sql}
        {where_sql}
        """
        # Pass search_params to filter the count correctly
        return conn.execute(count_query, search_params).fetchone()[0]

    def _get_pagination_limits(
        self, page_size: int, total_rows: int, offset: int
    ) -> tuple[int, int]:
        """
        Calculates the final LIMIT and OFFSET values, handling the 'fetch all' case.

        :param page_size: The requested items per page.
        :type page_size: int
        :param total_rows: The total number of rows available.
        :type total_rows: int
        :param offset: The calculated starting offset.
        :type offset: int
        :returns: A tuple of (limit, offset) to use in the main query.
        :rtype: tuple[int, int]
        """
        if page_size == 0:
            # Case: Fetch all releases
            return total_rows, 0
        else:
            return page_size, offset

    def _build_main_query(self, where_sql: str, order_clause: str) -> str:
        """
        Constructs the main SQL query for fetching release data.

        :param where_sql: The WHERE SQL fragment, including 'WHERE' if present.
        :type where_sql: str
        :param order_clause: The complete SQL fragment for the ORDER BY clause.
        :type order_clause: str
        :returns: The full parameterized SQL query string.
        :rtype: str
        """
        # Build the SELECT and JOIN clauses for the custom fields
        custom_select_sql, custom_join_sql = self._build_custom_field_joins()

        return f"""
        SELECT 
            r.id,
            REPLACE(GROUP_CONCAT(DISTINCT a.name), ',', ', ') as artist_name,
            r.title, 
            REPLACE(GROUP_CONCAT(DISTINCT l.name), ',', ', ') as label_name,
            REPLACE(GROUP_CONCAT(DISTINCT g.name), ',', ', ') as genres,
            REPLACE(GROUP_CONCAT(DISTINCT s.name), ',', ', ') as style_name,
            rl.catno, r.year, r.release_url, r.format, r.thumb_url
            {custom_select_sql}
        FROM releases r
        LEFT JOIN release_artists ra ON r.id = ra.release_id
        LEFT JOIN artists a ON ra.artist_id = a.id
        LEFT JOIN release_labels rl ON r.id = rl.release_id
        LEFT JOIN release_genres gs on r.id = gs.release_id
        LEFT JOIN genres g on gs.genre_id = g.id
        LEFT JOIN labels l ON rl.label_id = l.id
        LEFT JOIN release_styles rs on r.id = rs.release_id
        LEFT JOIN styles s on rs.style_id = s.id
        {custom_join_sql}
        {where_sql}
        GROUP BY r.id
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
        """

    def get_releases_paginated(self, request: PaginatedReleaseRequest):
        """
        Coordinates fetching releases with full support for search, sorting, and pagination.

        :param request: Request
        :type request: PaginatedReleaseRequest
        :return: Tuple containing the rows and total rows.
        :rtype: tuple(list, int)
        """
        # 1. Prepare SQL Components
        order_clause = self._build_order_clause(request.sort_by, request.desc)
        where_sql, search_params = self._build_where_clause(
            request.search_query,
            request.artist_ids,
            request.genre_ids,
            request.style_ids,
            request.label_ids,
            request.formats,
            request.custom_field_filters,
        )

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

        return rows, total_rows

    def get_all_artists(self):
        """
        Fetches all unique artists from the DB, sorted by sort_name.

        :returns: List of dictionaries with 'id', 'name', and 'sort_name'.
        :rtype: list[dict]
        """
        with self.get_db_connection() as conn:
            query = """
            SELECT 
                id, 
                name, 
                COALESCE(sort_name, name) AS sort_name_for_order
            FROM artists
            ORDER BY sort_name_for_order COLLATE NOCASE ASC;
            """
            cursor = conn.execute(query)
            # Use dict() to convert Row objects to dictionaries for easier consumption
            return [dict(row) for row in cursor.fetchall()]

    def get_artist_id_by_name(self, artist_name: str) -> int | None:
        """
        Fetches the ID of an artist given their exact name.

        :param artist_name: The name of the artist to search for.
        :returns: The integer ID of the artist, or None if not found.
        :rtype: int | None
        """
        with self.get_db_connection() as conn:
            query = """
            SELECT
                id
            FROM artists
            WHERE name = ?;
            """
            # Pass the artist_name as a tuple to the execute method.
            # This safely substitutes the '?' placeholder.
            cursor = conn.execute(query, (artist_name,))

            # Fetch the first (and only expected) result.
            # fetchone() returns a single Row object or None.
            row = cursor.fetchone()

            # Extract the 'id' from the row if it exists.
            return row["id"] if row else None

    def get_all_genres(self):
        """
        Fetches all unique genres from the DB.

        :returns: List of dictionaries with 'id' and 'name'.
        :rtype: list[dict]
        """
        with self.get_db_connection() as conn:
            query = """
            SELECT 
                id, 
                name
            FROM genres
            ORDER BY id;
            """
            cursor = conn.execute(query)
            # Use dict() to convert Row objects to dictionaries for easier consumption
            return [dict(row) for row in cursor.fetchall()]

    def get_genre_id_by_name(self, genre: str) -> int | None:
        """
        Fetches the ID of a genre given its exact name.

        :param genre: The name of the genre to search for.
        :returns: The integer ID of the genre, or None if not found.
        :rtype: int | None
        """
        with self.get_db_connection() as conn:
            query = """
            SELECT
                id
            FROM genres
            WHERE name = ?;
            """
            # Pass the artist_name as a tuple to the execute method.
            # This safely substitutes the '?' placeholder.
            cursor = conn.execute(query, (genre,))

            # Fetch the first (and only expected) result.
            # fetchone() returns a single Row object or None.
            row = cursor.fetchone()

            # Extract the 'id' from the row if it exists.
            return row["id"] if row else None

    def get_all_styles(self):
        """
        Fetches all unique styles from the DB.

        :returns: List of dictionaries with 'id' and 'name'.
        :rtype: list[dict]
        """
        with self.get_db_connection() as conn:
            query = """
            SELECT 
                id, 
                name
            FROM styles
            ORDER BY name;
            """
            cursor = conn.execute(query)
            # Use dict() to convert Row objects to dictionaries for easier consumption
            return [dict(row) for row in cursor.fetchall()]

    def get_style_id_by_name(self, style: str) -> int | None:
        """
        Fetches the ID of a style given its exact name.

        :param style: The name of the style to search for.
        :returns: The integer ID of the style, or None if not found.
        :rtype: int | None
        """
        with self.get_db_connection() as conn:
            query = """
            SELECT
                id
            FROM styles
            WHERE name = ?;
            """
            # Pass the artist_name as a tuple to the execute method.
            # This safely substitutes the '?' placeholder.
            cursor = conn.execute(query, (style,))

            # Fetch the first (and only expected) result.
            # fetchone() returns a single Row object or None.
            row = cursor.fetchone()

            # Extract the 'id' from the row if it exists.
            return row["id"] if row else None

    def get_all_labels(self):
        """
        Fetches all unique labels from the DB.

        :returns: List of dictionaries with 'id' and 'name'.
        :rtype: list[dict]
        """
        with self.get_db_connection() as conn:
            query = """
            SELECT 
                id, 
                name
            FROM labels
            ORDER BY name;
            """
            cursor = conn.execute(query)
            # Use dict() to convert Row objects to dictionaries for easier consumption
            return [dict(row) for row in cursor.fetchall()]

    def get_label_id_by_name(self, label: str) -> int | None:
        """
        Fetches the ID of a style given its exact name.

        :param label: The name of the label to search for.
        :returns: The integer ID of the label, or None if not found.
        :rtype: int | None
        """
        with self.get_db_connection() as conn:
            query = """
            SELECT
                id
            FROM labels
            WHERE name = ?;
            """
            # Pass the artist_name as a tuple to the execute method.
            # This safely substitutes the '?' placeholder.
            cursor = conn.execute(query, (label,))

            # Fetch the first (and only expected) result.
            # fetchone() returns a single Row object or None.
            row = cursor.fetchone()

            # Extract the 'id' from the row if it exists.
            return row["id"] if row else None

    def get_unique_formats(self) -> list[str]:
        """
        Fetches all unique formats from the releases table in the DB.

        :returns: List of unique format strings.
        :rtype: list[str]
        """
        with self.get_db_connection() as conn:
            query = """
            SELECT DISTINCT
                format
            FROM releases
            WHERE format IS NOT NULL AND format != ''
            ORDER BY format ASC;
            """
            cursor = conn.execute(query)
            # fetchall() returns a list of Row objects (which behave like tuples).
            # We use a list comprehension to extract the first (and only) column value (the format string).
            return [row[0] for row in cursor.fetchall()]

    def get_all_custom_field_values(self) -> Dict[int, List[str]]:
        """
        Fetches all unique values for each custom field from the DB,
        including a special (Blanks) option for NULL/empty values.

        :returns: A dictionary mapping field_id (int) to a list of unique values (str).
        :rtype: Dict[int, List[str]]
        """
        custom_field_data = {}
        with self.get_db_connection() as conn:
            for field_id in self.get_custom_field_ids_set():
                table_name = f"custom_field_{field_id}"

                # Fetch all values, including NULL/empty
                query = f"""
                SELECT DISTINCT
                    field_value
                FROM {table_name}
                ORDER BY field_value ASC;
                """
                cursor = conn.execute(query)

                values = []
                # has_blanks = False
                for row in cursor.fetchall():
                    value = row[0]
                    if value is None or (
                        isinstance(value, str) and value.strip() == ""
                    ):
                        # Found a blank or NULL value
                        # has_blanks = True
                        pass
                    else:
                        # Add non-blank values
                        values.append(value)

                values.insert(0, self.BLANKS_LABEL)  # Add it at the start

                custom_field_data[field_id] = values
        return custom_field_data
