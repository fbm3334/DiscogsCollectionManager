from nicegui import ui, app
from gui import DiscogsSorterGui

dsg = DiscogsSorterGui(force_fetch=False)

def root():
    dsg.build_root_elements()
    ui.sub_pages({'/': main, '/settings': settings})

def main():
    dsg.build_main_ui()

def settings():
    dsg.build_settings_page()

ui.run(root, favicon='🎧', title='Discogs Collection Manager')

app.timer(1, dsg.start_auto_refresh, once=True)