from pathlib import Path

import argparse
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


def run(args):
    process_db(args.filepath, args.outputpath)

def parse_cmdline():
    description = 'Forensics.im Dump Tool'
    parser = argparse.ArgumentParser(description=description)
    required_group = parser.add_argument_group('required arguments')
    required_group.add_argument('--filepath', required=True, help='File path to the IndexedDB.')
    required_group.add_argument('--outputpath', required=True, help='File path to the processed output.')
    args = parser.parse_args()
    return args

def cli():
    header = pyfiglet.figlet_format("Forensics.im Dump Tool")
    print(header)
    args = parse_cmdline()
    run(args)


if __name__ == '__main__':
    cli()
