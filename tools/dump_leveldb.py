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

import click

from forensicsim.backend import parse_db, write_results_to_json
from forensicsim.consts import DUMP_HEADER


def process_db(input_path, output_path):
    # Do some basic error handling
    if not input_path.parts[-1].endswith(".leveldb"):
        raise ValueError(f"Expected a leveldb folder. Path: {input_path}")

    # convert the database to a python list with nested dictionaries
    extracted_values = parse_db(input_path, do_not_filter=True)

    # write the output to a json file
    write_results_to_json(extracted_values, output_path)


@click.command()
@click.option(
    "-f",
    "--filepath",
    type=click.Path(
        exists=True, readable=True, writable=False, dir_okay=True, path_type=Path
    ),
    required=True,
    help="File path to the IndexedDB.",
)
@click.option(
    "-o",
    "--outputpath",
    type=click.Path(writable=True, path_type=Path),
    required=True,
    help="File path to the processed output.",
)
def process_cmd(filepath, outputpath):
    click.echo(DUMP_HEADER)
    process_db(filepath, outputpath)


if __name__ == "__main__":
    process_cmd()
