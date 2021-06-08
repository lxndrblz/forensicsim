import json
import logging
import time
from calendar import timegm

import click
import pause
import pyfiglet
from pywinauto import Desktop, keyboard
from pywinauto.application import Application

logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p', filename='data_population_skype.log',
                    level=logging.DEBUG)

# Lets assume Skype is not running
skype_window = Application(backend='uia').start(
    r"C:\Program Files (x86)\Microsoft\Skype for Desktop\skype.exe").connect(title='Skype', timeout=100)
# Wait until load screen passes
time.sleep(10)


def select_chat_channel(contact):
    # Select contact from sidebar
    chat = skype_window.Skype.child_window(title=contact, control_type="Text").wrapper_object()
    chat.click_input()


def react_to_last_message():
    # Ensure the chat is fully loaded
    time.sleep(5)
    # Like only the last Message
    react_buttons = skype_window.Skype.descendants(title="React to this message", control_type="Button")
    react_button = react_buttons[-1]
    react_button.click_input()
    time.sleep(2)
    # Like Response
    like_button = skype_window.Skype.child_window(title="Crying", control_type="Button").wrapper_object()
    like_button.click()
    logging.info('Reacted with Like to last message')


def remove_last_message(title):

    time.sleep(5)
    # skype_window.Skype.print_control_identifiers()
    # Select the last text message with a matching title
    text_boxes = skype_window.Skype.descendants(title=title, control_type="Text")
    print(text_boxes)
    text_box = text_boxes[-1]
    # Open the context menu
    text_box.click_input(button="right")
    time.sleep(3)
    # Click on the remove menu
    remove_button = skype_window.Skype.child_window(title="Remove", control_type="MenuItem").wrapper_object()
    remove_button.click_input()
    # Click remove once more to confirm
    remove_button_confirm = skype_window.Skype.child_window(title="Remove", control_type="Text").wrapper_object()
    remove_button_confirm.click_input()
    logging.info('Removed last message')


def send_text_message(message):
    message_box = skype_window.Skype.child_window(title="Type a message", control_type="Edit").wrapper_object()
    message_box.click_input()
    time.sleep(1)
    keyboard.send_keys(message, with_spaces=True)
    keyboard.send_keys('{ENTER}')
    logging.info(message)


def send_media_message(filepath):
    # Click the send button
    file_button = skype_window.Skype.child_window(title="Add files", control_type="Button").wrapper_object()
    file_button.click_input()
    # Navigate to the file
    file_window = Desktop().window(title="Open")
    file_window.type_keys(filepath + '{ENTER}', with_spaces=True)
    # Wait for the image to load
    time.sleep(10)
    message_box = skype_window.Skype.child_window(title="Type a message", control_type="Edit").wrapper_object()
    message_box.click_input()
    message_box.type_keys('{ENTER}', with_spaces=True)
    logging.info(filepath)


def populate_data_skype(all_data_to_populate, account):
    # Select the other account
    if account == '0':
        select_chat_channel("Jane Doe")
    else:
        select_chat_channel("John Doe")

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
                    remove_last_message(d["Content"])


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
        populate_data_skype(data, account)


if __name__ == '__main__':
    cli()
