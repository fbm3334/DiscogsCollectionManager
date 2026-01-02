"""
main.py

Main running file.
"""

# Python standard libraries
import argparse
from argparse import Namespace
import logging
import multiprocessing
from pathlib import Path
import shutil
from typing import Any

# PyPI libraries
from nicegui import ui, app

# DiscogsCollectionSorter classes
from gui.gui import DiscogsSorterGui

# This is required to allow the windowed GUI to work properly in Linux.
multiprocessing.set_start_method(method="spawn", force=True)

# Create the base GUI class.
dsg = DiscogsSorterGui()


def root():
    """Root function to create the root elements and build the subpages."""
    dsg.build_root_elements()
    ui.sub_pages(routes={"/": main, "/settings": settings})


def main():
    """Build the main UI."""
    dsg.build_main_ui()


def settings():
    """Build the settings page."""
    dsg.build_settings_page()

def clear_cache():
    """Clear the cache folder and remake it.
    """
    cache_folder = Path(__file__).resolve().parent.parent / "cache"
    shutil.rmtree(cache_folder)
    cache_folder.mkdir()

# Argument parsing code
parser = argparse.ArgumentParser(description="A tool for managing Discogs collections.")

parser.add_argument("-s", "--server", action="store_true", help="Activate server mode.")
parser.add_argument(
    "-d",
    "--debuglogging",
    action="store_true",
    help="Enable debug logging to terminal.",
)
parser.add_argument("-p", "--port", type=int, default=9876, help="Set a custom port.")
parser.add_argument("-c", "--clearcache", action="store_true", help="Clear the caches.")

args: Namespace = parser.parse_args()

server_mode: Any = args.server
debug_logging: Any = args.debuglogging
port: int = args.port
clear_cache_state: Any = args.clearcache

if clear_cache_state:
    dsg.clear_cache()

if debug_logging:
    log_level = logging.DEBUG
    print("Debug logging enabled")
else:
    log_level = logging.ERROR

logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True,
)

ui.run(
    root,
    favicon="🎧",
    title="Discogs Collection Manager",
    native=not server_mode,
    port=port,
    uvicorn_logging_level="debug" if debug_logging else "error",
)

app.timer(interval=5, callback=dsg.start_auto_refresh, once=True)
