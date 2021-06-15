:: Build the executable
pyinstaller --noconfirm --onefile --console --add-data "C:/Users/Alexander Bilz/AppData/Roaming/Python/Python39/site-packages/click;click/" --add-data "C:/Users/Alexander Bilz/AppData/Roaming/Python/Python39/site-packages/pyfiglet;pyfiglet/" --add-data "C:/Users/Alexander Bilz/AppData/Roaming/Python/Python39/site-packages/bs4;bs4/" --add-binary "C:/Program Files/Python39/python39.dll;."  "C:/dev/forensicsim/utils/main.py"
:: Copy the two files of interest into the Autopsy plugin directory - overwrite if necessary
xcopy /y "C:\dev\forensicsim\dist\main.exe" "C:\Users\Alexander Bilz\AppData\Roaming\autopsy\python_modules\forensicsim"
xcopy /y "C:\dev\forensicsim\Forensicsim_Parser.py" "C:\Users\Alexander Bilz\AppData\Roaming\autopsy\python_modules\forensicsim"



