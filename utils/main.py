import ast
import json
import re
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup

import click
import pyfiglet

from ccl_chrome_indexeddb import ccl_leveldb

ENCODING = "iso-8859-1"



def decode_value(b):
    # Cut off some unwanted HEX bytes
    try:
        b = b.replace(b'\x00', b'')
        b = b.replace(b'\x01', b'')
        b = b.replace(b'\x02', b'')
        b = b.replace(b'\xa0', b'')
        value = b.decode()

    except UnicodeDecodeError:
        try:
            value = b.decode('utf-8')
        except Exception:
            value = str(b)
    return value


def strip_html_tags(value):

    try:
        # Get the text of any embedded html, such as divs, a href links
        soup = BeautifulSoup(value, features="html.parser")
        text = soup.get_text()
        # remove new lines
        text = text.rstrip("\n")
        return text
    except:
        return value


def parse_db(filepath):
    fetched_ldb_records = []
    try:
        db = ccl_leveldb.RawLevelDb(filepath)
    except Exception as e:
        print(f' - Could not open {filepath} as LevelDB; {e}')

    try:
        for record in db.iterate_records_raw():
            # Ignore empty records
            if record.value is not None:
                fetched_ldb_records.append(record)
    except ValueError:
        print(f'Exception reading LevelDB: ValueError')
    except Exception as e:
        print(f'Exception reading LevelDB: {e}')
    # Close the database
    db.close()
    print(f'Reading {len(fetched_ldb_records)} Local Storage raw LevelDB records; beginning parsing')
    parse_records(fetched_ldb_records)


def get_nested_data_structures(record):
    nested_schemas = record.split(b'[{')[-1:]
    nested_schemas = nested_schemas[0].split(b'}]')[:-1]
    # Add search criteria back to the string to make list and dictionary structures complete again
    byte_str = b'[{' + nested_schemas[0] + b'}]'
    # turn the byte string into a Python list with dictionaries
    nested_dictionary = ast.literal_eval(byte_str.decode('utf-8'))
    return nested_dictionary

# The problem is that some content such as href links dont work with the splitting algorithm
def get_content(record):
    try:
        # Get the content record between content and renderContent keys
        content = record.split(b'content"')[-1:]
        content = content[0].split(b'"\rrenderContent"')[:-1]
        return content[0][1::]
    except:
        return record

def determine_record_type(record):
    types = {
        'reaction_in_chat': {'identifier': {b'activityType': 'reactionInChat'},
                             'fields': [b'activityType', b'messagetype', b'contenttype', b'activitySubtype',
                                        b'activityTimestamp', b'composetime', b'sourceUserImDisplayName'],
                             'nested_schema': None},
        'media': {'identifier': {b'messagetype': 'Text'},
                  'fields': [b'messagetype', b'imdisplayname', b'composetime', b'files'], 'nested_schema': b'files'},
        'message': {'identifier': {b'messagetype': 'RichText/Html'},
                    'fields': [b'messagetype', b'contenttype', b'imdisplayname', b'content', b'renderContent',
                               b'clientmessageid', b'composetime', b'originalarrivaltime', b'clientArrivalTime'],
                    'nested_schema': None},
        'call': {'identifier': {b'messagetype': 'Event/Call'},
                 'fields': [b'messagetype', b'displayName', b'originalarrivaltime', b'clientArrivalTime'],
                 'nested_schema': None},

    }

    for key in types:
        if record.find(b'"') != -1:
            t = True
            cleaned_record = {}
            key_values = record.split(b'"')
            for i, field in enumerate(key_values):
                # check if field is a key - ignore the first byte as it is usually junk
                if field[1::] in types[key]['fields']:
                    # use current field as key, use next field as value
                    cleaned_record[field[1::]] = strip_html_tags(decode_value(key_values[i + 1][1::]))
                # Get nested schemas, such as files
                if field[1::] == types[key]['nested_schema']:
                    nested = get_nested_data_structures(record)
                    cleaned_record[field[1::]] = nested

            # Determine the message type by checking if the identifiers match
            for identifier_key in types[key]['identifier']:
                if identifier_key in cleaned_record:
                    if cleaned_record[identifier_key] != types[key]['identifier'][identifier_key]:
                        t = False

            # Lets only consider the entries that are complete and that have a valid content type
            if t and all(c in cleaned_record for c in types[key]['fields']):
                cleaned_record[b'type'] = key
                if key == 'message':
                    # Patch the content of messages by specifically looking for divs
                    cleaned_record[b'content'] = strip_html_tags(decode_value(get_content(record)))
                return cleaned_record
    # No type could be determined
    return None


def parse_records(fetched_ldb_records):
    # Split up records by message type
    cleaned_records = []

    for f_byte in fetched_ldb_records:
        record = determine_record_type(f_byte.value)
        if record is not None:
            # Decode the dict keys
            cleaned_record = {key.decode(): val for key, val in record.items()}
            # Include additional information about the database record, such as file origin, and the state
            cleaned_record["origin_file"] = str(f_byte.origin_file)
            cleaned_record["file_type"] = f_byte.file_type.name
            cleaned_record["offset"] = f_byte.offset
            cleaned_record["seq"] = f_byte.seq
            cleaned_record["state"] = f_byte.state.name
            cleaned_record["was_compressed"] = f_byte.was_compressed
            cleaned_records.append(cleaned_record)

    # Filter by messages
    messages = [d for d in cleaned_records if d['type'] == 'message']
    parse_text_message(messages)

    # Filter by reactions
    # reactions = [d for d in cleaned_records if d['type'] == 'reaction_in_chat']
    # parse_message_reaction(reactions)
    #
    # Filter by media messages
    # media_messages = [d for d in cleaned_records if d['type'] == 'media']
    # parse_media_messages(media_messages)


def parse_message_reaction(messages):
    messages.sort(key=lambda date: datetime.strptime(date['composetime'][:19], "%Y-%m-%dT%H:%M:%S"))

    # TODO Show messages (id), which the user responded to
    for m in messages:
        print(f"Date: {m['composetime'][:19]} - User: {m['sourceUserImDisplayName']} - Liked Message in Chat")


def parse_media_messages(messages):
    messages.sort(key=lambda date: datetime.strptime(date['composetime'][:19], "%Y-%m-%dT%H:%M:%S"))

    for m in messages:
        # print all files that are attached to a message
        for file in m['files']:
            print(
                f"Date: {m['composetime'][:19]} - User: {m['imdisplayname']} - File: {file['fileName']} Path: {file['objectUrl']}")


def parse_text_message(messages):
    messages.sort(key=lambda date: datetime.strptime(date['composetime'][:19], "%Y-%m-%dT%H:%M:%S"))

    # Dump messages into a json file
    with open('messages.json', 'w') as f:
        json.dump(messages, f)

    # Print the text messages
    for m in messages:
        print(f"Compose Time: {m['composetime'][:19]} - User: {m['imdisplayname']} - Message: {m['content']}")


def read_input(filepath):
    # Do some basic error handling
    if not filepath.endswith('leveldb'):
        raise Exception('Expected a leveldb folder. Path: {}'.format(filepath))

    p = Path(filepath)
    if not p.exists():
        raise Exception('Given file path does not exists. Path: {}'.format(filepath))

    if not p.is_dir():
        raise Exception('Given file path is not a folder. Path: {}'.format(filepath))

    # TODO Possibly copy the artefacts before processing them?
    parse_db(filepath)


@click.command()
@click.option('--filepath', '-f', required=True, default='data/conversation.json',
              help="Relative file path to JSON with conversation data")
def cli(filepath):
    header = pyfiglet.figlet_format("Forensics.im Dump Tool")
    click.echo(header)
    read_input(filepath)


if __name__ == '__main__':
    cli()
