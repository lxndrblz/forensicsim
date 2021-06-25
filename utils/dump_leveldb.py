from pathlib import Path

import click
import pyfiglet

import shared


def process_db(filepath, output_path):
    # Do some basic error handling
    if not filepath.endswith('leveldb'):
        raise Exception('Expected a leveldb folder. Path: {}'.format(filepath))

    p = Path(filepath)
    if not p.exists():
        raise Exception('Given file path does not exists. Path: {}'.format(filepath))

    if not p.is_dir():
        raise Exception('Given file path is not a folder. Path: {}'.format(filepath))

    # convert the database to a python list with nested dictionaries
    extracted_values = shared.parse_db(filepath)

    # write the output to a json file
    shared.write_results_to_json(extracted_values, output_path)


@click.command()
@click.option('--filepath', '-f', required=True,
              default="\IndexedDB\https_teams.microsoft.com_0.indexeddb.leveldb",
              help="Relative file path to JSON with conversation data")
@click.option('--outputpath', '-o', required=True, default='teams.json',
              help="Relative file path to JSON with conversation data")
def cli(filepath, outputpath):
    header = pyfiglet.figlet_format("Forensics.im Dump Tool")
    click.echo(header)
    process_db(filepath, outputpath)


if __name__ == '__main__':
    cli()
