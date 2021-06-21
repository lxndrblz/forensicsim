import json
import logging
import os
import time
from calendar import timegm
from time import sleep

import click
import pause
import pyautogui
from pywinauto import keyboard
import pyfiglet

# Avoid the default link as it would update Teams on startup
os.startfile("C:/Users/forensics/AppData/Local/Microsoft/Teams/current/Teams.exe")
# Wait for Teams to start
sleep(50)
# Maximize the window
pyautogui.hotkey('win','up')
sleep(10)
# Move to chats tab
pyautogui.hotkey('ctrl', '2')

logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p',
                    filename='data_population_teams.log',
                    level=logging.DEBUG)

# TODO replace with final values
chat_partner_0 = "JaneDoe@forensics.im"
chat_partner_1 = "JohnDoe@forensics.im"

def select_chat_channel(contact):
    try:
        pyautogui.hotkey('ctrl', 'n')
        time.sleep(5)
        # use pywinauto cause pyautogui cant write an add symbol
        keyboard.send_keys(contact, with_spaces=True, pause=0.1)
        # Wait for suggestion to load
        time.sleep(5)
        # Confirm suggestion
        pyautogui.press('enter')
        time.sleep(3)
        pyautogui.press('enter')
        time.sleep(3)
        # Set focus to the text box
        # pyautogui.press('tab')
    except Exception as e:
        print(e)


def send_text_message(message):
    try:
        time.sleep(3)
        # use pywinauto to send non ASCII characters as well
        keyboard.send_keys(message, with_spaces=True)
        keyboard.send_keys('{ENTER}')
        logging.info(message)
    except Exception as e:
        print(e)


def send_media_message(filepath):
    try:
        pyautogui.hotkey('ctrl', 'o')
        time.sleep(10)
        # TODO Personal version of Teams does not need down/organisational does
        pyautogui.press('down')
        pyautogui.press('enter')
        time.sleep(5)
        pyautogui.write(filepath, interval=0.25)
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
        logging.info('Reacted with Heart to last message')
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

def start_audio_call():
    try:
        pyautogui.hotkey('ctrl', 'shift', 'c')
        logging.info('Started audio call')
    except Exception as e:
        print(e)

def end_audio_call():
    try:
        pyautogui.hotkey('ctrl', 'shift', 'b')
        logging.info('Ended audio call')
    except Exception as e:
        print(e)

def accept_audio_call():
    try:
        pyautogui.hotkey('ctrl', 'shift', 's')
        logging.info('Accepted audio call')
    except Exception as e:
        print(e)

def decline_audio_call():
    try:
        pyautogui.hotkey('ctrl', 'shift', 'd')
        logging.info('Declined audio call')
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
                    start_audio_call()
                if d["Type"] == "endcall":
                    end_audio_call()
                if d["Type"] == "acceptcall":
                    accept_audio_call()
                if d["Type"] == "declinecall":
                    decline_audio_call()

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
