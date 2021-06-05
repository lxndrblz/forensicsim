from datetime import datetime

import click
import pyfiglet
from ccl_chrome_indexeddb import ccl_leveldb
from pathlib import Path
import csv

ENCODING = "iso-8859-1"


def decode_value(b):
    try:
        value = b.replace(b'\x00', b'').decode()
    except UnicodeDecodeError:
        try:
            value = b.decode('utf-16')
        except Exception:
            value = str(b)
    return value


def parse_db(filepath):
    fetched_ldb_records = []
    try:
        db = ccl_leveldb.RawLevelDb(filepath)
    except Exception as e:
        print(f' - Could not open {filepath} as LevelDB; {e}')


    try:
        for record in db.iterate_records_raw():
            is_dictionary_key = True  # store current field state (key or value)
            key, value = '', ''
            out = {}
            # Ignore entries without a quotation mark as these do not represent the data structure we are looking for
            if record.value.find(b'"') != -1:
                # Split a record value by the quotation mark
                # TODO Fix an issue where nested schemas get lost
                for i, field in enumerate(record.value.split(b'"')):
                    if i == 0:  # skip first field
                        continue
                    le = len(field)
                    if not le:
                        continue
                    if le == 1:
                        is_dictionary_key = not is_dictionary_key
                        continue

                    elif (le - 1) > field[0]:
                        if is_dictionary_key:
                            key = decode_value(field[1:field[0] + 1])
                            value = field[field[0] + 1:]
                            out[key] = value

                        else:
                            value = field[1:field[0] + 1]
                            out[key] = value
                            is_dictionary_key = not is_dictionary_key
                        continue

                    if is_dictionary_key:
                        key = decode_value(field[1:])
                    else:
                        value = field[1:]
                        out[key] = decode_value(value)
                    is_dictionary_key = not is_dictionary_key
                fetched_ldb_records.append(out)

    except ValueError:
        print(f'Exception reading LevelDB: ValueError')

    except Exception as e:
        print(f'Exception reading LevelDB: {e}')
    # Close the database
    db.close()
    print(f'Reading {len(fetched_ldb_records)} Local Storage raw LevelDB records; beginning parsing')
    parse_records(fetched_ldb_records)


def parse_records(fetched_ldb_records):
    text_messages = []
    file_messages = []
    # Split up records by message type
    for f in fetched_ldb_records:
        try:
            if f['messagetype'] == 'RichText/Html' and f['composetime'] is not None:
                text_messages.append(f)
            elif f['messagetype'] == 'Text' and f['composetime'] is not None:
                print(f)
                file_messages.append(f)
        except:
            pass
    if text_messages is not None:
        parse_text_message(text_messages)


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


# Load conversation History from JSON
@click.command()
@click.option('--filepath', '-f', required=True, default='data/conversation.json',
              help="Relative file path to JSON with conversation data")
def cli(filepath):
    header = pyfiglet.figlet_format("Forensics.im")
    click.echo(header)
    read_input(filepath)


if __name__ == '__main__':
    cli()
