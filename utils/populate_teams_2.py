import json
import logging
import time
from calendar import timegm
from time import sleep

import click
import pause
import pyautogui
import pyfiglet
from pywinauto import keyboard

# Teams could be started from script, but requires change owner permissions. Better to launch Teams 2.0 first and
# then set the focus to the application.
# os.startfile("C:/Program Files/WindowsApps/MicrosoftTeams_21197.1103.908.5982_x64__8wekyb3d8bbwe/msteams.exe")

# Wait for Teams to start
sleep(50)
# Maximize the window
pyautogui.hotkey('win', 'up')
sleep(10)
# Move to chats tab
pyautogui.hotkey('ctrl', '2')

logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p',
                    filename='data_population_teams.log',
                    level=logging.DEBUG)

chat_partner_0 = "JaneDoe@forensics.im"
chat_partner_1 = "JohnDoe@forensics.im"


def send_text_message(message):
    try:
        time.sleep(3)
        # use pywinauto to send non ASCII characters as well
        keyboard.send_keys(message, with_spaces=True)
        keyboard.send_keys('{ENTER}')
        # logging.info(message)
    except Exception as e:
        print(e)


def send_media_message(filepath):
    try:
        pyautogui.hotkey('ctrl', 'o')
        time.sleep(10)
        # TODO Personal version of Teams does not need down/organisational does
        # pyautogui.press('down')
        pyautogui.press('enter')
        time.sleep(5)
        pyautogui.write(filepath, interval=0.25)
        time.sleep(5)
        pyautogui.press('enter')
        time.sleep(30)
        pyautogui.press('enter')
        logging.info(filepath)
    except Exception as e:
        print(e)


def simulate_empty_input():
    # simulate input to ensure messages loaded correctly
    pyautogui.press('x')
    time.sleep(2)
    pyautogui.press('backspace')
    time.sleep(2)


def react_to_last_message():
    # Sends a heart
    try:
        simulate_empty_input()
        # select last message
        pyautogui.hotkey('shift', 'tab')
        time.sleep(2)
        pyautogui.press('enter')
        pyautogui.press('enter')
        time.sleep(2)
        pyautogui.press('esc')
        time.sleep(2)
        pyautogui.press('tab')
        logging.info('Reacted to last message')
    except Exception as e:
        print(e)


def remove_last_message():
    try:
        pyautogui.hotkey('shift', 'tab')
        time.sleep(2)
        pyautogui.press('enter')
        pyautogui.press('tab')
        pyautogui.press('enter')
        time.sleep(2)
        pyautogui.press(['down', 'down'])
        pyautogui.press('enter')
        time.sleep(2)
        pyautogui.press('tab')
        logging.info('Removed last message')
    except Exception as e:
        print(e)


def populate_data_teams(all_data_to_populate, account):
    # TODO Account swithing does not work reliably. Therefore, accounts have to be selected manually after startup.
    # Select the other account
    # if account == '0':
    #     select_chat_channel(chat_partner_0)
    # else:
    #     select_chat_channel(chat_partner_1)

    with click.progressbar(all_data_to_populate) as data:
        for d in data:
            # Convert data to EPOCH assume GMT time
            utc_time = time.strptime(d["Time"], "%Y-%m-%dT%H:%M:%S")
            epoch_time = timegm(utc_time)
            # Sleep both accounts to wait for reply
            pause.until(epoch_time)
            # Carry Out action on the corresponding account
            if d["Account"] == account:
                if d["Type"] == "message":
                    send_text_message(d["Content"])
                if d["Type"] == "media":
                    send_media_message(d["Content"])
                if d["Type"] == "react":
                    react_to_last_message()
                if d["Type"] == "delete":
                    remove_last_message()
                if d["Type"] == "startcall":
                    # Currently not available in teams 2
                    pass
                if d["Type"] == "endcall":
                    # Currently not available in teams 2
                    pass
                if d["Type"] == "acceptcall":
                    # Currently not available in teams 2
                    pass
                if d["Type"] == "declinecall":
                    # Currently not available in teams 2
                    pass


# Load conversation History from JSON
@click.command()
@click.option('--filepath', '-f', required=True, default='data/conversation.json',
              help="Relative file path to JSON with conversation data")
@click.option('--account', '-a', required=True, default='0', help='Account to populate')
def cli(filepath, account):
    header = pyfiglet.figlet_format("Forensics.im Util")
    click.echo(header)
    with click.open_file(filepath, encoding="utf-8") as f:
        data = json.load(f)
        populate_data_teams(data, account)


if __name__ == '__main__':
    cli()
