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
        # remove junk
        text = text.replace('\x00', '')
        text = text.replace('\x01', '')
        text = text.replace('\x02', '')
        text = text.replace('\x03', '')
        text = text.replace('\xa0', '')
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


def get_nested_data_structures(record, schema):
    nested_schemas = record.value.split(b'[{'+schema)[-1:]
    nested_schemas = nested_schemas[0].split(b'}]')[:-1]
    # Add search criteria back to the string to make list and dictionary structures complete again
    byte_str = b'[{'+schema + nested_schemas[0] + b'}]'
    # turn the byte string into a Python list with dictionaries
    nested_dictionary = ast.literal_eval(byte_str.decode('utf-8'))
    return nested_dictionary

def get_content(record):
    # This destinction is necessary, as chinese messages would not decode correctly
    utf16_encoded = record.value.decode('utf-16', 'replace')
    utf8_encoded = record.value.decode('utf-8', 'replace')

    # UTF-16 messages
    if b'"\x07contentc' in record.value:
        content_utf16_encoded = utf16_encoded.split('</div>')[0]
        content_utf16_encoded = content_utf16_encoded.split('<div>')[1]
        return content_utf16_encoded
    # UTF-8 Messages
    elif b'"\x07content' in record.value:
        content_utf8_encoded = utf8_encoded.split('"\rrenderContent')[0]
        content_utf8_encoded = content_utf8_encoded.split('"\x07content')[1]
        return content_utf8_encoded[2::]

def determine_record_type(record):
    message_types = {
        'reaction_in_chat': {'identifier': {b'activityType': 'reactionInChat'},
                             'fields': [b'activityType', b'messagetype', b'contenttype', b'activitySubtype',
                                        b'activityTimestamp', b'composetime', b'sourceUserImDisplayName']},
        'plain': {'identifier': {b'messagetype': 'Text'},
                  'fields': [b'messagetype', b'imdisplayname', b'composetime']},
        'message': {'identifier': {b'messagetype': 'RichText/Html'},
                    'fields': [b'messagetype', b'contenttype', b'imdisplayname', b'clientmessageid', b'composetime', b'originalarrivaltime', b'clientArrivalTime']},
        'call': {'identifier': {b'messagetype': 'Event/Call'},
                 'fields': [b'messagetype', b'displayName', b'originalarrivaltime', b'clientArrivalTime']}

    }
    # Lets identify nested schemas based the the schema type
    # TODO implement Hyplinks Type
    nested_schema = {
        # 'hyperlinks': {'identifier': b'"@type":"http://schema.skype.com/HyperLink"'},
        'files': {'identifier': b'"@type":"http://schema.skype.com/File"'}
    }

    for key in message_types:
        if record.value.find(b'"') != -1:
            t = True
            cleaned_record = {}
            key_values = record.value.split(b'"')
            for i, field in enumerate(key_values):
                # check if field is a key - ignore the first byte as it is usually junk
                if field[1::] in message_types[key]['fields']:
                    # use current field as key, use next field as value
                    cleaned_record[field[1::]] = strip_html_tags(decode_value(key_values[i + 1][1::]))
            # Get nested schemas, such as files or hyperlinks, could be both
            cleaned_record[b'nested_content'] = []
            for schema in nested_schema:
                if nested_schema[schema]['identifier'] in record.value:
                    cleaned_record[b'nested_content'].append(get_nested_data_structures(record, nested_schema[schema]['identifier']))

            # Determine the message type by checking if the identifiers match
            for identifier_key in message_types[key]['identifier']:
                if identifier_key in cleaned_record:
                    if cleaned_record[identifier_key] != message_types[key]['identifier'][identifier_key]:
                        t = False

            # Lets only consider the entries that are complete and that have a valid content type
            if t and all(c in cleaned_record for c in message_types[key]['fields']):
                cleaned_record[b'type'] = key
                if key == 'message':
                    # Patch the content of messages by specifically looking for divs
                    cleaned_record[b'content'] = strip_html_tags(get_content(record))
                return cleaned_record
    # No type could be determined
    return None


def parse_records(fetched_ldb_records):
    # Split up records by message type
    cleaned_records = []

    for fetched_record in fetched_ldb_records:
        record = determine_record_type(fetched_record)
        if record is not None:
            # Decode the dict keys
            cleaned_record = {key.decode(): val for key, val in record.items()}
            # Include additional information about the database record, such as file origin, and the state
            cleaned_record["origin_file"] = str(fetched_record.origin_file)
            cleaned_record["file_type"] = fetched_record.file_type.name
            cleaned_record["offset"] = fetched_record.offset
            cleaned_record["seq"] = fetched_record.seq
            cleaned_record["state"] = fetched_record.state.name
            cleaned_record["was_compressed"] = fetched_record.was_compressed
            cleaned_records.append(cleaned_record)
            print(cleaned_record)

    # Filter by messages
    #messages = [d for d in cleaned_records if d['type'] == 'message']
    #parse_text_message(messages)

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