import click
import pyfiglet

from pathlib import Path
from ccl_chrome_indexeddb import ccl_leveldb


def read_input(filepath, search_string):
    # Do some basic error handling
    if not filepath.endswith('leveldb'):
        raise Exception('Expected a leveldb folder. Path: {}'.format(filepath))

    p = Path(filepath)
    if not p.exists():
        raise Exception('Given file path does not exists. Path: {}'.format(filepath))

    if not p.is_dir():
        raise Exception('Given file path is not a folder. Path: {}'.format(filepath))

    # TODO Possibly copy the artefacts before processing them?
    parse_db(filepath, search_string)

def parse_db(filepath, searchstring):
    try:
        db = ccl_leveldb.RawLevelDb(filepath)
    except Exception as e:
        print(f' - Could not open {filepath} as LevelDB; {e}')

    try:
        for record in db.iterate_records_raw():
            # Ignore empty records
            if str.encode(searchstring) in record.value:
                print(record.value)
                print("*"*20)
    except ValueError:
        print(f'Exception reading LevelDB: ValueError')
    except Exception as e:
        print(f'Exception reading LevelDB: {e}')
    # Close the database
    db.close()


@click.command()
@click.option('--filepath', '-f', required=True, default='data/conversation.json',
              help="Relative file path to JSON with conversation data")

@click.option('--searchstring', '-s', required=True, default='',
              help="String to search for")

def cli(filepath, searchstring):
    header = pyfiglet.figlet_format("Forensics.im Search Tool")
    click.echo(header)
    read_input(filepath, searchstring)


if __name__ == '__main__':
    cli()
