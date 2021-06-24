import ast
import json
from datetime import datetime
from datetime import date
from pathlib import Path

import click
import pyfiglet
from bs4 import BeautifulSoup

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


def parse_db(filepath, outputpath):
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
    parse_records(fetched_ldb_records, outputpath)


def get_nested_data_structures(record, schema):
    nested_schemas = record.split(b'[{' + schema)[-1:]
    nested_schemas = nested_schemas[0].split(b'}]')[:-1]
    # Add search criteria back to the string to make list and dictionary structures complete again
    byte_str = b'[{' + schema + nested_schemas[0] + b'}]'
    # turn the byte string into a Python list with dictionaries
    content_utf8_encoded = byte_str.decode('utf-8')
    content_utf8_encoded = replace_literal(content_utf8_encoded)
    nested_dictionary = ast.literal_eval(content_utf8_encoded)
    return nested_dictionary


def get_content(record):
    # This destinction is necessary, as chinese messages would not decode correctly
    utf16_encoded = record.decode('utf-16', 'replace')
    utf8_encoded = record.decode('utf-8', 'replace')

    # UTF-16 messages
    if b'"\x07contentc' in record:
        content_utf16_encoded = utf16_encoded.split('</div>')[0]
        content_utf16_encoded = content_utf16_encoded.split('<div>')[1]
        return content_utf16_encoded
    # UTF-8 Messages
    elif b'"\x07content' in record:
        content_utf8_encoded = utf8_encoded.split('"\rrenderContent')[0]
        content_utf8_encoded = content_utf8_encoded.split('"\x07content')[1]
        return content_utf8_encoded[2::]


def replace_literal(record):
    record = record.replace(":null", ":None")
    record = record.replace(":false", ":False")
    record = record.replace(":true", ":True")
    return record


def get_meeting(record):
    utf8_encoded = record.decode('utf-8', 'replace')
    # grep the meeting json
    content_utf8_encoded = utf8_encoded.split('"\x07meeting"')[1]
    content_utf8_encoded = content_utf8_encoded.split('"\nthreadType')[0]
    # replace null with null, false and true otherwise it throws an error
    content_utf8_encoded = replace_literal(content_utf8_encoded)
    # Convert string into a dictionary, skip the first two byte
    return ast.literal_eval(content_utf8_encoded[2::])


def get_call(record):
    utf8_encoded = record.decode('utf-8', 'replace')
    # grep the meeting json
    content_utf8_encoded = utf8_encoded.split('"\x08call-log"')[1]
    content_utf8_encoded = content_utf8_encoded.split('"\x0es2spartnername"')[0]
    # replace null with null, false and true otherwise it throws an error
    content_utf8_encoded = replace_literal(content_utf8_encoded)
    # Convert string into a dictionary, skip the first two byte
    return ast.literal_eval(content_utf8_encoded[2::])


def get_emotion(record):
    utf8_encoded = record.decode('utf-8', 'replace')
    # grep the meeting json
    content_utf8_encoded = utf8_encoded.split('"\x08emotionso"')[1]
    content_utf8_encoded = content_utf8_encoded.split('I\x02{')[0]
    # replace null with null, false and true otherwise it throws an error
    content_utf8_encoded = replace_literal(content_utf8_encoded)
    # Convert string into a dictionary, skip the first two byte
    return content_utf8_encoded[1::]


def get_delete_time(record):
    utf8_encoded = record.decode('utf-8', 'replace')
    # grep the delete time in milliseconds
    content_utf8_encoded = utf8_encoded.split('"\ndeletetime"')[1]
    content_utf8_encoded = content_utf8_encoded.split('"\nimportanceI')[0]
    # Make a nice formatted time out of the timestamp
    return convert_time_stamps(content_utf8_encoded)


def get_edit_time(record):
    utf8_encoded = record.decode('utf-8', 'replace')
    # grep the version timestamp in milliseconds
    content_utf8_encoded = utf8_encoded.split('"\x07version"')[1]
    content_utf8_encoded = content_utf8_encoded.split('"\x13messageStorageStateI')[0]
    # Make a nice formatted time out of the timestamp
    return convert_time_stamps(content_utf8_encoded)


def convert_time_stamps(content_utf8_encoded):
    # timestamp appear in epoch format with milliseconds alias currentmillis
    # Convert data to neat timestamp
    delete_time_datetime = datetime.utcfromtimestamp(int(content_utf8_encoded) / 1000)
    delete_time_string = delete_time_datetime.strftime('%Y-%m-%dT%H:%M:%S.%f')

    return str(delete_time_string)


def determine_record_type(record):
    message_types = {
        'meeting': {'identifier': {b'type': 'Meeting', b'messagetype': 'ThreadActivity/AddMember'},
                    'fields': [b'type', b'messagetype', b'id', b'composetime', b'originalarrivaltime',
                               b'clientArrivalTime', b'cachedDeduplicationKey']},
        'reaction_in_chat': {'identifier': {b'activityType': 'reactionInChat', b'contenttype': 'text'},
                             'fields': [b'activityType', b'messagetype', b'contenttype', b'activitySubtype',
                                        b'originalarrivaltime', b'clientmessageid', b'creator',
                                        b'activityTimestamp', b'composetime', b'sourceUserImDisplayName']},
        'reaction': {'identifier': {b'activityType': 'reaction', b'contenttype': 'text'},
                     'fields': [b'activityType', b'messagetype', b'contenttype', b'originalarrivaltime',
                                b'clientmessageid', b'creator',
                                b'activityTimestamp', b'composetime', b'sourceUserImDisplayName', b'activitySubtype']},
        'reply': {'identifier': {b'activityType': 'reply', b'contenttype': 'text'},
                  'fields': [b'activityType', b'messagetype', b'contenttype', b'messagePreview', b'clientmessageid',
                             b'activityTimestamp', b'composetime', b'originalarrivaltime', b'sourceUserImDisplayName',
                             b'creator']},
        'call': {'identifier': {b'messagetype': 'RichText/Html', b'contenttype': 'text'},
                 'fields': [b'messagetype', b'originalarrivaltime', b'clientArrivalTime', b'clientmessageid',
                            b'composetime', b'originalarrivaltime', b'clientArrivalTime', b'call-log']},
        'message': {'identifier': {b'messageKind': 'skypeMessageLocal', b'contenttype': 'text'},
                    'fields': [b'conversationId', b'messagetype', b'contenttype', b'imdisplayname',
                               b'clientmessageid', b'composetime', b'originalarrivaltime', b'creator',
                               b'clientArrivalTime', b'cachedDeduplicationKey']},
        'contact': {'identifier': {b'userType': 'Member'},
                    'fields': [b'displayName', b'mri', b'email', b'userPrincipalName']}
    }
    # Lets identify nested schemas based the the schema type
    nested_schema = {
        'hyperlinks': {'identifier': b'"@type":"http://schema.skype.com/HyperLink"'},
        'files': {'identifier': b'"@type":"http://schema.skype.com/File"'}
    }

    records_in_db_record = []
    # TODO Split posts into sub messages
    # delimeter = b'"\x0bmessagetype'
    # # Consider only messages with a valid messagetype
    # if record.value.find(delimeter) != -1:
    #     # Posts contain multiple messages in one database record that is why it is necessary to split
    #     if(record.value.find(delimeter) > 1):
    #
    #         records_in_db_record = [e+delimeter for e in record.value.split(delimeter) if e]
    #         print(records_in_db_record)
    #     else:
    #         records_in_db_record.append(record.value)
    records_in_db_record.append(record.value)
    cleaned_records = []

    for r in records_in_db_record:
        for key in message_types:
            if r.find(b'"') != -1:
                t = True
                cleaned_record = {}
                key_values = r.split(b'"')

                for i, field in enumerate(key_values):
                    # check if field is a key - ignore the first byte as it is usually junk
                    # Only add each key only once
                    if field[1::] in message_types[key]['fields'] and field[1::] not in cleaned_record:
                        # use current field as key, use next field as value
                        cleaned_record[field[1::]] = strip_html_tags(decode_value(key_values[i + 1][1::]))
                # Get nested schemas, such as files or hyperlinks, could be both
                cleaned_record[b'nested_content'] = []
                for schema in nested_schema:
                    if nested_schema[schema]['identifier'] in r:
                        cleaned_record[b'nested_content'].append(
                            get_nested_data_structures(r, nested_schema[schema]['identifier']))

                # Determine the message type by checking if the identifiers match
                for identifier_key in message_types[key]['identifier']:
                    if identifier_key in cleaned_record:
                        if cleaned_record[identifier_key] != message_types[key]['identifier'][identifier_key]:
                            t = False

                # Lets only consider the entries that are complete and that have a valid content type
                if t and all(c in cleaned_record for c in message_types[key]['fields']):
                    cleaned_record[b'type'] = key
                    # Check for some additional operations, if the type is a message
                    if key == 'message':
                        # Check for emotions such as likes, hearts, grumpy face
                        if b'\x08emotionso' in key_values:
                            cleaned_record[b'emotion'] = get_emotion(r)
                        else:
                            cleaned_record[b'emotion'] = None

                        # Mark a record as deleted
                        if b'\ndeletetime' in key_values:
                            cleaned_record[b'deleted'] = get_delete_time(r)
                        else:
                            cleaned_record[b'deleted'] = None

                        # Mark a record as edited and get the latest version timestamp
                        if b'\x07version' in key_values:
                            cleaned_record[b'edited'] = get_edit_time(r)
                        else:
                            cleaned_record[b'edited'] = None

                        if b'\x08isFromMeT' in key_values:
                            cleaned_record[b'isFromMe'] = True
                        else:
                            cleaned_record[b'isFromMe'] = False

                        # Patch the content of messages by specifically looking for divs
                        cleaned_record[b'content'] = strip_html_tags(get_content(r))

                    # Do some further processing for message types that have nested JSONs, but not schemas.
                    if key == 'meeting':
                        meeting_details = get_meeting(r)
                        cleaned_record[b'content'] = meeting_details
                    elif key == 'call':
                        call_details = get_call(r)
                        cleaned_record[b'call-log'] = call_details
                    cleaned_records.append(cleaned_record)

    return cleaned_records


def parse_records(fetched_ldb_records, outputpath):
    # Split up records by message type
    parsed_records = []

    for fetched_record in fetched_ldb_records:
        records = determine_record_type(fetched_record)
        if records is not None:
            for record in records:
                # Decode the dict keys
                cleaned_record = {key.decode(): val for key, val in record.items()}
                # Include additional information about the database record, such as file origin, and the state
                cleaned_record["origin_file"] = str(fetched_record.origin_file)
                cleaned_record["file_type"] = fetched_record.file_type.name
                cleaned_record["offset"] = fetched_record.offset
                cleaned_record["seq"] = fetched_record.seq
                cleaned_record["state"] = fetched_record.state.name
                cleaned_record["was_compressed"] = fetched_record.was_compressed
                parsed_records.append(cleaned_record)

    # Remove duplicates based on their deduplication key at least for the entries that have a cacheDeduplicationKey
    # distinct_records = [i for n, i in enumerate(parsed_records) if
    #                     i.get('cachedDeduplicationKey') not in [y.get('cachedDeduplicationKey') for y in
    #                                                             parsed_records[n + 1:]]]
    #
    # # Add the entries without a cachedDeduplicationKey, these are filtered based on the clientmessageid
    # dirty_records = [d for d in parsed_records if 'cachedDeduplicationKey' not in d]
    # clean_records = [i for n, i in enumerate(dirty_records) if
    #                  i.get('clientmessageid') not in [y.get('clientmessageid') for y in dirty_records[n + 1:]]]
    #
    # distinct_records = distinct_records + clean_records
    # write_results_to_json(distinct_records, outputpath)

    # TODO enable deduplication again

    write_results_to_json(parsed_records, outputpath)

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

    # Print the text messages
    for m in messages:
        print(f"Compose Time: {m['composetime'][:19]} - User: {m['imdisplayname']} - Message: {m['content']}")


def write_results_to_json(data, outputpath):
    # Dump messages into a json file
    with open(outputpath, 'w') as f:
        json.dump(data, f)


def read_input(filepath, outputpath):
    # Do some basic error handling
    if not filepath.endswith('leveldb'):
        raise Exception('Expected a leveldb folder. Path: {}'.format(filepath))

    p = Path(filepath)
    if not p.exists():
        raise Exception('Given file path does not exists. Path: {}'.format(filepath))

    if not p.is_dir():
        raise Exception('Given file path is not a folder. Path: {}'.format(filepath))

    # TODO Possibly copy the artefacts before processing them?
    parse_db(filepath, outputpath)


@click.command()
@click.option('--filepath', '-f', required=True, default='data/conversation.json',
              help="Relative file path to JSON with conversation data")
@click.option('--outputpath', '-o', required=False, default='teams.json',
              help="Relative file path to JSON with conversation data")
def cli(filepath, outputpath):
    header = pyfiglet.figlet_format("Forensics.im Dump Tool")
    click.echo(header)
    read_input(filepath, outputpath)


if __name__ == '__main__':
    cli()
