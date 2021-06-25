from pathlib import Path

import click
import pyfiglet

import shared
from ccl_chrome_indexeddb import ccl_chromium_indexeddb


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


def parse_db(filepath, outputpath):
    wrapper = ccl_chromium_indexeddb.WrappedIndexDB(filepath)

    extracted_values = []
    for wrapped_db in wrapper.database_ids:
        db = wrapper[wrapped_db.dbid_no]
        print("***** Processing Database *****")
        print(f"database number: {db.db_number} database name: {db.name} database origin: {db.origin}")
        print("*** Processing Object Stores ***")
        for object_store_name in db.object_store_names:
            object_store = db[object_store_name]
            print(f"object stored id: {object_store.object_store_id} object store name: {object_store.name}")
            try:
                for record in object_store.iterate_records():
                    extracted_values.append(
                        {'database': db.name, 'store': object_store_name, 'key': record.key, 'value': record.value})
            except StopIteration as e:
                print(e)
    shared.write_results_to_json(extracted_values, outputpath)


@click.command()
@click.option('--filepath', '-f', required=True,
              default='..\testdata\IndexedDB\https_teams.microsoft.com_0.indexeddb.leveldb',
              help="Relative file path to JSON with conversation data")
@click.option('--outputpath', '-o', required=True, default='teams.json',
              help="Relative file path to JSON with conversation data")
def cli(filepath, outputpath):
    header = pyfiglet.figlet_format("Forensics.im Dump Tool")
    click.echo(header)
    read_input(filepath, outputpath)


if __name__ == '__main__':
    cli()
