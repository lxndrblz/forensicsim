"""
MIT License

Copyright (c) 2021 Alexander Bilz

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from pathlib import Path

import argparse
import pyfiglet
import pyfiglet.fonts

import shared


def process_db(filepath, output_path):
    # Do some basic error handling

    p = Path(filepath)
    if not p.exists():
        raise Exception('Given file path does not exists. Path: {}'.format(filepath))

    if not p.is_dir():
        raise Exception('Given file path is not a folder. Path: {}'.format(filepath))

    # convert the database to a python list with nested dictionaries
    extracted_values = shared.parse_localstorage(p)

    # write the output to a json file
    shared.write_results_to_json(extracted_values, output_path)


def run(args):
    process_db(args.filepath, args.outputpath)

def parse_cmdline():
    description = 'Forensics.im Dump Local Storage'
    parser = argparse.ArgumentParser(description=description)
    required_group = parser.add_argument_group('required arguments')
    required_group.add_argument('-f', '--filepath', required=True, help='File path to the IndexedDB.')
    required_group.add_argument('-o', '--outputpath', required=True, help='File path to the processed output.')
    args = parser.parse_args()
    return args

def cli():
    header = pyfiglet.figlet_format("Forensics.im Dump Tool")
    print(header)
    args = parse_cmdline()
    run(args)


if __name__ == '__main__':
    cli()
