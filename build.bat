:: Build the executable
pyinstaller "main.spec"
:: Copy the two files of interest into the Autopsy plugin directory - overwrite if necessary
xcopy /y "dist\ms_teams_parser.exe" "%appdata%\autopsy\python_modules\forensicsim"
xcopy /y "Forensicsim_Parser.py" "%appdata%\autopsy\python_modules\forensicsim"

