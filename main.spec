# -*- mode: python ; coding: utf-8 -*-

block_cipher = None


a = Analysis(['utils\\main.py'],
             binaries=[],
             datas=[('c:/hostedtoolcache/windows/python/3.9.13/x64/lib/site-packages/pyfiglet', 'pyfiglet')],
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name='ms_teams_parser',
          debug=False,
          strip=False,
          upx=True,
          runtime_tmpdir=None,
          console=True )
