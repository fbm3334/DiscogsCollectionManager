from datetime import datetime, timezone
import shutil
from typing import List, Dict, Any

from nicegui import ui, run
import tomlkit as tk
from tomlkit import TOMLDocument
from tomlkit.exceptions import NonExistentKey

from core.discogs_conn import DiscogsConn
from core.core_classes import PaginatedReleaseRequest
from gui.gui_classes import SidebarPage, IDFilterDefinition, StringFilterDefinition
from gui.gui_constants import PAGES, FILTER_DEFINITIONS, STATIC_COLUMNS


class DiscogsSorterGui:
    """
    Discogs sorter GUI frontend class.
    """

    INITIAL_PAGE_SIZE = 20
    INITIAL_PAGE = 0
    BLANKS_LABEL = "[Blanks]"

    def __init__(self) -> None:
        """
        Class initialisation method.
        """
        self.backend = DiscogsConn()

        self._initialise_state_variables()
        self._perform_initial_fetch()
        self._get_lists_filters()

        self.format_list = self.backend.get_unique_formats()

        self.custom_field_data: Dict[int, List[str]] = (
            self.backend.get_all_custom_field_values()
        )
        self.custom_field_filter_ids: dict[int, list[str]] | None = None

        self.load_toml_config()

    def _initialise_state_variables(self):
        """
        Initialise all of the state variables to set up the GUI.
        """
        # Blank config
        self.config: TOMLDocument

        # Current page
        self.current_page_key = 0

        # Personal access token
        self.entered_pat = None

        # Strings
        self.search_query = ""
        self.progress_string = ""
        self.progress_stage = ""

        # Filter IDs
        self.artist_filter_ids = None
        self.genre_filter_ids = None
        self.style_filter_ids = None
        self.label_filter_ids = None
        self.format_selected_list = None

        # Refresh state
        self.refresh_flag = False
        self.refresh_progress_area = None
        self.refresh_spinner = None

        # Blank table
        self.table: ui.table

    def _perform_initial_fetch(self):
        """
        Perform an initial fetch of the data from the backend to display it
        in the table.
        """
        # Fetch initial releases
        initial_request = PaginatedReleaseRequest(
            page=0, page_size=20, sort_by="artist", desc=False
        )
        self.releases, self.num_releases = self.backend.get_releases_paginated(
            request=initial_request
        )

        # Table code inspired by https://github.com/zauberzeug/nicegui/discussions/1903#discussioncomment-8251437
        self.table_data = {
            "rows": self.releases,
            "pagination": {
                "page": self.INITIAL_PAGE,
                "rowsPerPage": self.INITIAL_PAGE_SIZE,
                "rowsNumber": self.num_releases,
            },
        }

    def _dict_to_list_conversion(self, raw_dict: List[Dict[str, Any]]) -> List[str]:
        """
        Convert a list of dictionaries into a list so it can be represented
        properly in the GUI.

        :param raw_dict: Raw list of dictionaries.
        :type raw_dict: List[Dict[str, Any]]
        :return: List containing the items in the dictionaries.
        :rtype: List[str]
        """
        return [item.get("name", self.BLANKS_LABEL) for item in raw_dict]

    def _get_lists_filters(self):
        """
        Create the lists to be used for filtering.
        """
        self.artist_list = self._dict_to_list_conversion(self.backend.get_all_artists())
        self.genre_list = self._dict_to_list_conversion(self.backend.get_all_genres())
        self.style_list = self._dict_to_list_conversion(self.backend.get_all_styles())
        self.label_list = self._dict_to_list_conversion(self.backend.get_all_labels())

    def load_toml_config(self):
        """
        Load the custom configuraton if it exists, else copy the default
        config.
        """
        # Try to load the config from config.toml
        try:
            with open("cache/config.toml", "r", encoding="utf-8") as f:
                self.config = tk.load(f)
        except FileNotFoundError:
            # If the file isn't found, then copy over the default config
            # and load it.
            shutil.copyfile("defaultconfig.toml", "cache/config.toml")
            with open("cache/config.toml", "r", encoding="utf-8") as f:
                self.config = tk.load(f)

    def save_toml_config(self):
        """
        Save the TOML config.
        """
        with open("cache/config.toml", "w", encoding="utf-8") as f:
            tk.dump(self.config, f)

    def _get_custom_field_columns(self) -> List[Dict[str, Any]]:
        """
        Generates custom field columns from the dynamically configured custom
        fields.

        :return: List of custom field columns, each item being a dictionary.
        :rtype: List[Dict[str, Any]]
        """
        custom_columns = []

        # Safely get the CustomFields configuration section, defaulting to an empty dict
        custom_field_config = self.config.get("CustomFields", {})

        for custom_field_id in self.backend.get_custom_field_ids_set():
            field_key = f"field_{custom_field_id}"

            # Use dict.get() for safer lookup instead of try/except
            # tk.TOMLDocument behaves like a dict here
            name = custom_field_config.get(field_key)

            if name is None:
                # Create the default name if the key doesn't exist in config
                name = f"Custom Field {custom_field_id}"

            field_name = f"custom_{custom_field_id}"

            custom_columns.append(
                {
                    "name": field_name,
                    "label": name,
                    "field": field_name,
                    "sortable": True,
                    "style": "text-wrap: wrap",
                }
            )
        return custom_columns

    def get_columns(self) -> List[Dict[str, Any]]:
        """
        Gets the columns of the table.

        :return: A list containing column dictionaries.
        :rtype: list
        """
        column_list = list(STATIC_COLUMNS)
        column_list.extend(self._get_custom_field_columns())

        return column_list

    def _toggle_columns(self, column: dict, visible: bool):
        """
        Toggle columns to show/hide them.

        :param column: Column to toggle.
        :type column: dict
        :param visible: Visibility status
        :type visible: bool
        """
        column["classes"] = "" if visible else "hidden"
        column["headerClasses"] = "" if visible else "hidden"
        self.table.update()

    def get_full_count(self) -> int:
        """
        Get the count of releases and save the count (equal to the number of
        rows).

        :return: Count of releases.
        :rtype: int
        """
        request = PaginatedReleaseRequest(page=0, page_size=1)
        _, count = self.backend.get_releases_paginated(request)
        self.table_data["pagination"]["rowsNumber"] = count
        return count

    def _normalise_pagination_request(self, request: Any) -> dict:
        """
        Normalises the pagination request from a NiceGUI request or a manual
        dictionary.

        :param request: Request to normalise.
        :type request: Any
        :return: Dictionary containing the normalised request.
        :rtype: dict
        """
        if isinstance(request, dict):
            return request.get("args", {}).get("pagination", {})

        # Assumes request is a NiceGUI Request object if not a dict
        return getattr(request, "args", {}).get("pagination", {})

    def do_pagination(self, request):
        """
        Handles the table requests for searching, sorting and pagination,
        and updates the table data accordingly.

        :param request: Request for table
        """
        new_pagination = self._normalise_pagination_request(request)

        pagination = self.table_data["pagination"]
        pagination.update(new_pagination)
        pagination_sort = new_pagination.get("sortBy", "artist")

        pagination_sort = (
            "artist" if pagination_sort == "artist_name" else pagination_sort
        )

        pagination_desc = new_pagination.get("descending", False)

        if pagination_sort is None:
            pagination_sort = "artist"
            pagination_desc = False

        request = PaginatedReleaseRequest(
            page=pagination["page"] - 1,
            page_size=pagination["rowsPerPage"],
            sort_by=pagination_sort,
            desc=pagination_desc,
            search_query=self.search_query,
            artist_ids=self.artist_filter_ids,
            genre_ids=self.genre_filter_ids,
            style_ids=self.style_filter_ids,
            label_ids=self.label_filter_ids,
            formats=self.format_selected_list,
            custom_field_filters=self.custom_field_filter_ids,
        )

        new_rows, count = self.backend.get_releases_paginated(request)

        self.table_data["pagination"]["rowsNumber"] = count

        self.table_data["rows"] = new_rows
        self.paginated_table.refresh()

    def _send_manual_pagination_request(self):
        """
        Send a manual pagination request.
        """
        self.table_data["pagination"]["page"] = 1
        manual_request = {
            "args": {
                "pagination": {
                    "page": 1,  # First page
                    "rowsPerPage": self.table_data["pagination"]["rowsPerPage"],
                    "sortBy": self.table_data["pagination"].get("sortBy", "artist"),
                    "descending": self.table_data["pagination"].get(
                        "descending", False
                    ),
                }
            }
        }
        self.do_pagination(manual_request)

    def search_callback(self, query):
        """
        Search callback function when the search box is updated.

        :param query: Search query
        """
        self.search_query = query.value
        self._send_manual_pagination_request()

    def _generic_select_callback(self, filter_type: str, id_lookup_method, query):
        """
        A generic callback function for all ID-based selection filters
        (Artist, Genre, Style, Label).

        :param filter_type: The base name of the filter ('artist', 'genre', 'style', 'label').
        :type filter_type: str
        :param id_lookup_method: The DiscogsManager method used to find the ID by name.
        :param query: The multiselect query object from NiceGUI (contains selected values).
        """
        name_list = query.value
        id_list = []

        for name in name_list:
            # Calls self.manager.get_artist_id_by_name(name) or similar
            id_list.append(id_lookup_method(name))

        # Dynamically set the correct filter attribute
        # Example: If filter_type is 'artist', this sets self.artist_filter_ids
        attribute_name = f"{filter_type}_filter_ids"

        if id_list:
            setattr(self, attribute_name, id_list)
            print(f"Set {attribute_name}: {id_list}")  # Replace with proper logging
        else:
            setattr(self, attribute_name, None)

        # Trigger the UI update
        self._send_manual_pagination_request()

    def _generic_string_callback(self, attribute_name: str, query):
        """
        A generic callback function for string-based selection filters (e.g., Format).

        :param attribute_name: The name of the instance attribute to update (e.g., 'format_selected_list').
        :param query: The multiselect query object (contains selected values).
        """
        selected_values = query.value

        if selected_values:
            # Set the attribute to the list of selected strings
            setattr(self, attribute_name, selected_values)
            print(
                f"Set {attribute_name}: {selected_values}"
            )  # Replace with proper logging
        else:
            # Clear the filter
            setattr(self, attribute_name, None)

        self._send_manual_pagination_request()

    def custom_field_select_callback(self, field_id: int, query):
        """
        Callback function for custom field selection.

        :param field_id: The ID of the custom field (e.g., 1, 2, 3).
        :param query: The multiselect query object (contains selected values).
        """
        selected_values = query.value  # This is a list of strings

        if not self.custom_field_filter_ids:
            self.custom_field_filter_ids = {}

        if selected_values:
            # Store the selected values for this specific field ID
            self.custom_field_filter_ids[field_id] = selected_values
        elif field_id in self.custom_field_filter_ids:
            # If no values are selected, remove the filter for this field ID
            del self.custom_field_filter_ids[field_id]

        # If the dictionary is empty after deletion, set to None
        if not self.custom_field_filter_ids:
            self.custom_field_filter_ids = None

        self._send_manual_pagination_request()

    @ui.refreshable
    def paginated_table(self):
        """
        Function to render the paginated table.
        """

        self.table = ui.table(
            rows=self.table_data["rows"],
            columns=self.get_columns(),
            pagination=self.table_data["pagination"],
            row_key="name",
        )
        self.table.add_slot(
            "body-cell-release_url",
            """
            <q-td :props="props">
                <u><a :href="props.value">Link</a></u>
            </q-td>
        """,
        )
        self.table.add_slot(
            "body-cell-thumb",
            """
            <q-td :props="props">
                <img :src="props.value" style="max-width: 50px; max-height: 50px;">
            </q-td>
        """,
        )

        self.table.classes("virtual-scroll h-[calc(100vh-200px)] w-full max-w-none")
        self.table.on("request", self.do_pagination)

    def discogs_connection_toggle_callback(self):
        """
        Discogs connection toggle callback function.
        """
        self.save_pat_callback()
        try:
            result = self.backend.toggle_discogs_connection()
            if result is True:
                ui.notify(f"Discogs connected as user {self.backend.user.username}.")
            else:
                ui.notify("Discogs disconnected.")
        except ValueError:
            ui.notify("No personal access token entered.", type="warning")

    def save_pat_callback(self):
        """
        Save the new personal access token.
        """
        if self.entered_pat is not None:
            self.backend.save_token(self.entered_pat.value)

    def user_settings_dialog_callback(self):
        """
        User settings dialog callback.
        """
        self.user_settings_dialog.open()

    @ui.refreshable
    def build_settings_menu(self):
        """
        Build the settings menu with callbacks etc.
        """
        with ui.row().classes("items-center justify-between w-70"):
            if self.backend.user is not None:
                ui.label(f"Connected as {self.backend.user.username}")
            else:
                ui.label("Disconnected from Discogs")
            ui.space()
            with ui.button(icon="settings"):
                with ui.menu().props("auto-close"):
                    # Check whether Discogs is connected or not
                    if self.backend.user is not None:
                        ui.menu_item(
                            "Disconnect from Discogs",
                            on_click=self.discogs_connection_toggle_callback,
                        )
                    else:
                        ui.menu_item(
                            "Connect to Discogs",
                            on_click=self.discogs_connection_toggle_callback,
                        )
                    ui.menu_item(
                        "User settings", on_click=self.user_settings_dialog_callback
                    )
                    ui.menu_item("Refresh", on_click=self.start_refresh)

    async def start_refresh(self):
        """
        Asynchronously start a refresh from the Discogs API.
        """
        if self.refresh_flag is False:
            self.refresh_flag = True
            self.refresh_spinner.set_visibility(True)
            # self.refresh_progress_area.set_visibility(True)
            try:
                self.discogs_connection_toggle_callback()
            except ValueError:
                ui.notify(
                    "Could not refresh - go to User Settings \
                           to add a personal access token.",
                    type="warning",
                )
                # self.user_settings_dialog_callback()
                self.refresh_flag = False
                return
            ui.notify("Started refresh...")
            self.progress_stage = "Fetching collection"
            await run.io_bound(self.backend.fetch_collection)
            ui.notify("Fetching artist sort names...")
            self.progress_stage = "Fetching artist sort names"
            await run.io_bound(
                self.backend.fetch_artist_sort_names, self.update_progress_string
            )
            ui.notify("Refresh complete.")
            self._send_manual_pagination_request()
            self.paginated_table.refresh()
            print("All done")
            self.refresh_flag = False
            self.config["Updates"]["update_time"] = datetime.now(timezone.utc)
            self.save_toml_config()
            self.refresh_spinner.set_visibility(False)
            self.progress_string = ""
            self.footer_update_text.refresh()
            self.footer_text.refresh()

    async def start_auto_refresh(self):
        """
        Start an auto-refresh if the conditions allow:

        - Auto-update is enabled.
        - Enough time has elapsed.
        """
        if self.config["Updates"]["auto_update"] is True:
            current_time = datetime.now(timezone.utc).timestamp()
            prev_time = self.config["Updates"]["update_time"].timestamp()
            update_interval_secs = self.config["Updates"]["update_interval"] * 60 * 60
            time_diff = current_time - prev_time

            if time_diff > update_interval_secs:
                self.config["Updates"]["update_time"] = datetime.now(timezone.utc)
                self.save_toml_config()
                await self.start_refresh()
            else:
                print("Not auto updating.")

    def update_progress_string(self, current, total):
        """
        Update the progress string.

        :param current: Current number.
        :param total: Total number.
        """
        progress_percentage = (current / total) * 100.0
        self.progress_string = f"{self.progress_stage} ({progress_percentage:.1f}%)"
        self.footer_update_text.refresh()

    # Adjust the type hint to accept either of the new dataclasses
    def _build_select_filter(
        self, definition: IDFilterDefinition | StringFilterDefinition
    ):
        """Builds a single ui.select element based on the provided dataclass definition."""

        # 1. Get the list of options from the instance attribute (e.g., self.artist_list)
        options_list = getattr(self, definition.data_list_attr)

        # 2. Determine the correct callback logic
        if definition.callback_type == "string":
            # --- String-based filter (Format) ---
            # The IDE knows 'definition' is a StringFilterDefinition here
            callback = lambda query: self._generic_string_callback(
                definition.attribute_name, query
            )
        else:
            # --- ID-based filter (Artist, Genre, etc.) ---
            # The IDE knows 'definition' is an IDFilterDefinition here

            # Get the actual manager method (e.g., self.manager.get_artist_id_by_name)
            lookup_method = getattr(self.backend, definition.manager_lookup)

            callback = lambda query: self._generic_select_callback(
                definition.filter_type, lookup_method, query
            )

        # 3. Build the UI element
        ui.select(
            options_list,
            multiple=True,
            label=definition.label,  # Use dot notation
            with_input=True,
            on_change=callback,
        ).classes("w-70").props("use-chips")

    def build_filter_dropdowns(self):
        """
        Build the filter dropdowns.
        """
        for definition in FILTER_DEFINITIONS:
            self._build_select_filter(definition)

        for field_id, values in self.custom_field_data.items():
            # Get the user-defined name from the config (or default)
            try:
                name = self.config["CustomFields"][f"field_{field_id}"]
            except NonExistentKey:
                name = f"Custom Field {field_id}"

            # Use a lambda function to pass the field_id to the callback
            ui.select(
                values,
                multiple=True,
                label=f"{name} Filter",
                with_input=True,
                on_change=lambda query, id=field_id: self.custom_field_select_callback(
                    id, query
                ),
            ).classes("w-70").props("use-chips")

    def navigate_refresh_left_drawer(self, page_key):
        """
        Navigate to the next page and refresh the left drawer.

        :param page: Description
        """
        self.current_page_key = page_key

        # Find the page data using the key
        target_page = next((p for p in PAGES if p.key == page_key), None)

        if target_page:
            ui.navigate.to(target_page.route)
        else:
            # Handle case where key is not found (optional)
            print(f"Error: Page with key {page_key} not found.")

        self.build_left_drawer.refresh()

    @ui.refreshable
    def build_left_drawer(self):
        """
        Build the left drawer.
        """
        selected_page_class = "bg-gray-300 font-bold"
        deselected_page_class = ""

        with ui.list().classes("w-full"):
            # Loop through the list of SidebarPage objects
            for page in PAGES:
                is_selected = self.current_page_key == page.key

                with ui.item(
                    on_click=lambda p=page: self.navigate_refresh_left_drawer(p.key)
                ).classes(
                    selected_page_class if is_selected else deselected_page_class
                ):
                    with ui.item_section().props("avatar"):
                        ui.icon(page.icon)
                    with ui.item_section():
                        ui.item_label(page.label)

    def _build_discogs_access_token_settings(self):
        """
        Build the Discogs access token settings.
        """
        ui.label("Discogs Settings").classes("text-xl font-bold")
        ui.label("Discogs Access Token").classes("text-l font-bold")
        ui.markdown(
            "Go to the [Discogs developers](https://www.discogs.com/settings/developers) settings page to generate a personal access token."
        )
        with ui.row().classes("items-center"):
            self.entered_pat = ui.input(
                label="Paste the personal access token here"
            ).classes("w-70")
            with ui.button_group():
                ui.button("Save", on_click=self.save_pat_callback)
                ui.button("Connect", on_click=self.discogs_connection_toggle_callback)

    def _build_update_settings(self):
        """
        Build the update settings.
        """
        ui.label("Update Settings").classes("text-xl font-bold")
        with ui.row().classes("items-center w-full"):
            ui.label("Auto-update")
            ui.space()
            ui.switch(on_change=lambda: self.save_toml_config()).bind_value(
                self.config["Updates"], "auto_update"
            )
        with ui.row().classes("items-center w-full"):
            ui.label("Auto-update interval (hours)")
            ui.space()
            ui.number(
                precision=0, on_change=lambda: self.save_toml_config()
            ).bind_value(self.config["Updates"], "update_interval")
        with ui.row().classes("items-center w-full"):
            ui.label("Update date/time display format -")
            ui.link(
                "strftime.org gives a list of the codes",
                target="https://strftime.org",
                new_tab=True,
            )
            ui.space()
            ui.textarea(on_change=lambda: self.save_toml_config()).bind_value(
                self.config["Updates"], "update_time_display_format"
            )

    def _build_custom_field_name_settings(self):
        """
        Build the custom field name settings.
        """
        # Check to see if CustomFields is in the config file first, and if not,
        # create it
        if "CustomFields" not in self.config:
            new_table = tk.table(is_super_table=True)
            self.config.add("CustomFields", new_table)

        ui.label("Custom Field Names").classes("text-xl font-bold")
        for label in self.backend.get_custom_field_ids_set():
            with ui.row().classes("items-center w-full"):
                ui.label(f"Custom field {label} name")
                ui.space()
                ui.input(on_change=lambda: self.save_toml_config()).bind_value(
                    self.config["CustomFields"], f"field_{label}"
                )

    def _column_show_hide_callback(self, column: dict, visible: bool):
        """
        Column show and hide callback - toggles the column as well as saves the
        config.

        :param column: Column to toggle.
        :type column: dict
        :param visible: Visibility status
        :type visible: bool
        """
        print(column, visible)
        self._toggle_columns(column, visible)
        self.table.update()
        self.save_toml_config()
        pass

    def _make_column_config_list(self):
        """
        Make the column configuration list.
        """
        # Check if the table name is in the document and create if not
        table_name = "ColumnVisibility"

        if table_name not in self.config:
            new_table = tk.table(is_super_table=True)
            self.config.add(table_name, new_table)

        config_table = self.config[table_name]

        for column in self.table.columns:
            # If the value exists, then create the key-value pairs
            # If the field doesn't exist in the config table, create it, else
            # update the table accordingly
            if column["field"] not in config_table:
                config_table[column["field"]] = True
            else:
                self._toggle_columns(column, config_table[column["field"]])

    def _build_column_show_hide_settings(self):
        """
        Build the column show/hide settings.
        """
        self._make_column_config_list()
        for column in self.table.columns:
            table_name = "ColumnVisibility"
            ui.checkbox(
                column["label"],
                on_change=lambda e, column=column: self._column_show_hide_callback(
                    column, e.value
                ),
            ).bind_value(self.config[table_name], column["field"])

    def build_settings_page(self):
        """
        Build the settings page.
        """
        self._build_discogs_access_token_settings()
        ui.separator().classes("w-full")
        self._build_update_settings()
        ui.separator().classes("w-full")
        self._build_custom_field_name_settings()

    def build_root_elements(self):
        """
        Build the root elements of the user interface (i.e. that will show on
        every page).
        """
        with ui.header(elevated=True).classes("bg-gray-900 text-white shadow-lg"):
            ui.button(on_click=lambda: left_drawer.toggle(), icon="menu")
            ui.label("Discogs Collection Manager").classes("text-3xl font-extrabold")

        with ui.left_drawer() as left_drawer:
            self.build_left_drawer()

        with ui.right_drawer(
            value=False, top_corner=False, bottom_corner=False, elevated=True
        ) as self.right_drawer:
            ui.button(on_click=self.right_drawer.hide, icon="close")
            self.build_filter_dropdowns()

        with ui.footer().classes("bg-gray-900 text-white shadow-lg items-center p-1"):
            self.footer_text()
            ui.space()
            self.footer_update_text()
            self.refresh_spinner = ui.spinner(color="white")
            self.refresh_spinner.set_visibility(False)

    @ui.refreshable
    def footer_text(self):
        """
        Function for the footer text - updateable.
        """
        formatted_string = self.config["Updates"]["update_time"].strftime(
            self.config["Updates"]["update_time_display_format"]
        )
        ui.markdown(f"**Last update:** {formatted_string}")
        if self.backend.user is not None:
            ui.icon("link", size="24px").classes("p-0")
            ui.label(f"Connected to Discogs as {self.backend.user.username}")
        else:
            ui.icon("link_off", size="24px").classes("p-0")
            ui.label("Disconnected from Discogs")

    @ui.refreshable
    def footer_update_text(self):
        """
        Function for footer update text - updateable.
        """
        ui.label(f"{self.progress_string}")

    @ui.refreshable
    def _build_column_show_hide_button(self):
        """
        Build a refreshable element for the column show/hide button.

        This is to avoid an AttributeError when the paginated table has not yet
        been created.
        """
        try:
            with ui.button("Show/Hide Columns"):
                with ui.menu(), ui.column().classes("gap-0 p-2"):
                    self._build_column_show_hide_settings()
        except AttributeError:
            print("Show/hide button not added.")

    def build_main_ui(self):
        """
        Build the main UI.
        """
        with ui.row().classes(
            "items-center justify-between content-between w-full bg-clip-padding"
        ):
            ui.input("Search", on_change=self.search_callback).props(
                "clearable rounded outlined dense"
            )
            ui.button(icon="refresh", on_click=self.start_refresh)
            ui.space()
            self._build_column_show_hide_button()
            ui.button(
                text="Filters", icon="filter_alt", on_click=self.right_drawer.toggle
            )

        self.paginated_table()
        self.table.update()
        self._build_column_show_hide_button.refresh()
