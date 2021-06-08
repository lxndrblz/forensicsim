from datetime import datetime

import click
import pyfiglet
from ccl_chrome_indexeddb import ccl_leveldb
from pathlib import Path
import re
import ast
import json

ENCODING = "iso-8859-1"


def decode_value(b):
    # Cut off some unwanted HEX bytes
    try:
        b = b.replace(b'\x00', b'')
        b = b.replace(b'\x01', b'')
        b = b.replace(b'\x02', b'')
        value = b.decode()

    except UnicodeDecodeError:
        try:
            value = b.decode('utf-16')
        except Exception:
            value = str(b)
    return value

def strip_html_tags(value):
    try:
        value = re.findall(r'<div>(.*)</div>', value)[0]
        return value
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


def parse_records_test(fetched_ldb_records):

    for f in fetched_ldb_records:
        if b'react' in f.value:
            print(f)

def parse_records(fetched_ldb_records):


    COMMON_FIELDS = [b'messagetype', b'contenttype',b'content', b'renderContent', b'clientmessageid',b'imdisplayname', b'composetime', b'originalarrivaltime', b'clientArrivalTime']
    NESTED_SCHEMAS = [b'files']
    cleaned_records = []
    # Split up records by message type
    # TODO Identify remaining message types and add theese
    for f_byte in fetched_ldb_records:
        record = f_byte.value
        if b'like' in record:
            print(record)
        cleaned_record = {}
        if record.find(b'"') != -1:
            # Split a record value by the quotation mark
            key_values = record.split(b'"')
            for i, field in enumerate(key_values):
                # check if field is a key - ignore the first byte as it is usually junk
                if field[1::] in COMMON_FIELDS:
                    # use current field as key, use next field as value
                    cleaned_record[field[1::]] = strip_html_tags(decode_value(key_values[i+1][1::]))
                if field[1::] in NESTED_SCHEMAS:
                    cleaned_record[field[1::]] = get_nested_data_structures(record)
                # Check if our dictionary is empty
        if bool(cleaned_record):
            # Decode the keys from bytes
            cleaned_record = { key.decode(): val for key, val in cleaned_record.items() }
            #record_dict = ast.literal_eval(decode_value(cleaned_record))
            # Include complete record for debugging purpose
            # record_dict['raw'] = f
            cleaned_records.append(cleaned_record)

    # Sorth the entries in ascending order
    cleaned_records.sort(key=lambda r: datetime.strptime(r['composetime'][:19], "%Y-%m-%dT%H:%M:%S"))

    with open('dumped_database.json', 'w') as f:
        json.dump(cleaned_records, f)



def parse_text_message(messages):

    # Sort messages by compose date
    # Data format 2021-06-01T12:47:45.926Z
    # TODO miliseconds should not be cut off
    messages.sort(key=lambda date: datetime.strptime(date['composetime'][:19], "%Y-%m-%dT%H:%M:%S"))

    # Print the text messages
    for f in messages:
        try:
            print(f"Date: {f['composetime'][:19]} - User: {f['imdisplayname']} - Message: {f['content']}")
        except:
            pass

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
