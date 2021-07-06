"""
MIT License

Copyright (c) 2021 Alexander Bilz

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from pathlib import Path

import wx

import shared


class DataRecord:
    def __init__(self, key, value, store):
        self.key = key
        self.value = value
        self.store = store


class DetailView(wx.Dialog):
    def __init__(self, db_record):
        title = "Detail View"
        super().__init__(parent=None, title=title)
        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        self.logs = wx.TextCtrl(self, id=-1, value='', pos=wx.DefaultPosition,
                                size=(-1, 300),
                                style=wx.TE_MULTILINE | wx.SUNKEN_BORDER)
        self.logs.AppendText(db_record.value + "\n")
        self.main_sizer.Add(self.logs, 0, wx.ALL | wx.EXPAND, 5)
        self.SetSizer(self.main_sizer)


class DBScoutPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        # Setup a searchbox
        self.search = wx.SearchCtrl(self, size=(200, -1), style=wx.TE_PROCESS_ENTER)
        self.search.ShowCancelButton(True)
        # List the key value pairs
        self.list_ctrl = wx.ListCtrl(
            self, size=(-1, 400),
            style=wx.LC_REPORT | wx.BORDER_SUNKEN
        )
        self.list_ctrl.InsertColumn(0, 'Key', width=140)
        self.list_ctrl.InsertColumn(1, 'Value', width=200)
        self.list_ctrl.InsertColumn(2, 'Origin', width=140)
        # Add a button for showing the active entry
        self.show_button = wx.Button(self, label='Show')
        self.show_button.Bind(wx.EVT_BUTTON, self.on_show)

        main_sizer.Add(self.search, 0, wx.ALL | wx.EXPAND, 15)
        main_sizer.Add(self.list_ctrl, 0, wx.ALL | wx.EXPAND, 15)
        main_sizer.Add(self.show_button, 0, wx.ALL | wx.EXPAND, 15)
        self.SetSizer(main_sizer)
        self.Bind(wx.EVT_SEARCHCTRL_SEARCH_BTN, self.OnSearch, self.search)
        self.Bind(wx.EVT_SEARCH_CANCEL, self.OnSearchCancel, self.search)
        self.leveldb = []
        self.leveldb_unfiltered = []

    def on_show(self, event):
        selection = self.list_ctrl.GetFocusedItem()
        if selection >= 0:
            entry = self.leveldb[selection]
            dlg = DetailView(entry)
            dlg.ShowModal()
            dlg.Destroy()

    def setup_list_ctr(self):
        self.list_ctrl.ClearAll()
        self.list_ctrl.InsertColumn(0, 'Key', width=140)
        self.list_ctrl.InsertColumn(1, 'Value', width=200)
        self.list_ctrl.InsertColumn(2, 'Origin', width=140)

    def insert_list_item(self, i, extracted_value):
        self.list_ctrl.InsertItem(i, extracted_value.key)
        self.list_ctrl.SetItem(i, 1,
                               extracted_value.value)
        self.list_ctrl.SetItem(i, 2,
                               extracted_value.store)

    def OnSearchCancel(self, evt):
        self.leveldb = self.leveldb_unfiltered
        for i, extracted_value in enumerate(self.leveldb):
            self.insert_list_item(i, extracted_value)

    def OnSearch(self, evt):
        value = self.search.GetValue()
        self.setup_list_ctr()
        i = 0
        updated_list = []
        for extracted_value in self.leveldb:
            if str(value) in extracted_value.value:
                updated_list.append(extracted_value)
                self.insert_list_item(i, extracted_value)
                i += 1
        self.leveldb = updated_list

    def list_click(self, event):
        index = event.GetSelection()
        selection = self.leveldb[index]
        wx.MessageBox(selection)

    def update_leveldb_listing(self, filepath):
        self.setup_list_ctr()
        # Do some basic error handling
        if not filepath.endswith('leveldb'):
            raise Exception('Expected a leveldb folder. Path: {}'.format(filepath))

        p = Path(filepath)
        if not p.exists():
            raise Exception('Given file path does not exists. Path: {}'.format(filepath))

        if not p.is_dir():
            raise Exception('Given file path is not a folder. Path: {}'.format(filepath))

        # convert the database to a python list with nested dictionaries
        extracted_records = shared.parse_db(filepath)
        processed_records = []
        for record in extracted_records:
            try:
                processed_records.append(
                    DataRecord(str(record['key']), str(record['value']), str(record['origin_file'])))
            except UnicodeDecodeError:
                continue

        self.leveldb = processed_records
        self.leveldb_unfiltered = processed_records
        for i, extracted_value in enumerate(processed_records):
            self.insert_list_item(i, extracted_value)


class DBScoutFrame(wx.Frame):
    def __init__(self):
        super().__init__(parent=None,
                         title='Forensics.im LevelDB Scout')
        self.panel = DBScoutPanel(self)
        self.create_menu()
        self.SetIcon(wx.Icon("resources/favicon.ico", wx.BITMAP_TYPE_ICO))
        self.Show()
        self.SetMaxSize((1920, 1080))
        self.SetMinSize((1024, 600))

    def create_menu(self):
        menu_bar = wx.MenuBar()
        file_menu = wx.Menu()
        open_folder_menu_item = file_menu.Append(
            wx.ID_ANY, 'Open LevelDB',
            'Open a LevelDB'
        )
        menu_bar.Append(file_menu, '&File')
        self.Bind(
            event=wx.EVT_MENU,
            handler=self.on_open_folder,
            source=open_folder_menu_item,
        )
        self.SetMenuBar(menu_bar)

    def on_open_folder(self, event):
        title = "Choose a directory:"
        dlg = wx.DirDialog(self, title,
                           style=wx.DD_DEFAULT_STYLE)
        if dlg.ShowModal() == wx.ID_OK:
            self.panel.update_leveldb_listing(dlg.GetPath())
        dlg.Destroy()

    def OnExit(self, evt):
        self.Destroy()

    def OnMax(self, evt):
        self.SetSize(self.MaxSize)

    def OnMin(self, evt):
        self.SetSize(self.MinSize)


if __name__ == '__main__':
    app = wx.App()
    frame = DBScoutFrame()
    app.MainLoop()
