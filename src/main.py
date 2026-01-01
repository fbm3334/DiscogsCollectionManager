'''
main.py

Main running file.
'''

import argparse
from argparse import Namespace
import logging
import multiprocessing
from typing import Any

from nicegui import ui, app

from gui.gui import DiscogsSorterGui

logging.basicConfig(
    level=logging.DEBUG
)

multiprocessing.set_start_method(method="spawn", force=True)

dsg = DiscogsSorterGui()


def root():
    dsg.build_root_elements()
    ui.sub_pages(routes={"/": main, "/settings": settings})


def main():
    dsg.build_main_ui()


def settings():
    dsg.build_settings_page()


parser = argparse.ArgumentParser(
    description="A tool for managing Discogs collections. Use --server to run in server mode (not windowed.)"
)

parser.add_argument("--server", action="store_true", help="Activate server mode.")

args: Namespace = parser.parse_args()

server_mode: Any = args.server

logging.log(logging.DEBUG, f"Server mode is {'Active' if server_mode else 'Inactive (windowed mode)'}")

ui.run(root, favicon="🎧", title="Discogs Collection Manager", native=not server_mode, port=9876)

app.timer(interval=5, callback=dsg.start_auto_refresh, once=True)
