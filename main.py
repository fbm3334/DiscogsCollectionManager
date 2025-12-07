from nicegui import ui, app
from gui import DiscogsSorterGui

dsg = DiscogsSorterGui(force_fetch=False)

def root():
    dsg.build_root_elements()
    ui.sub_pages({'/': main, '/settings': settings})

def main():
    dsg.build_main_ui()

def settings():
    ui.label('Another page content')
    ui.link('Go to main page', '/')

ui.run(root)

app.timer(1, dsg.start_auto_refresh, once=True)