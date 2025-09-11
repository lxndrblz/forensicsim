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

import json
from pathlib import Path
from typing import Any, Optional

from ccl_chromium_reader import (
    ccl_chromium_indexeddb,
    ccl_chromium_localstorage,
    ccl_chromium_sessionstorage,
)

TEAMS_DB_OBJECT_STORES = ["replychains", "conversations", "people", "buddylist"]

ENCODING = "iso-8859-1"


def parse_db(
    filepath: Path,
    blobpath: Optional[Path] = None,
    filter_db_results: Optional[bool] = True,
) -> list[dict[str, Any]]:
    # Open raw access to a LevelDB and deserialize the records.

    wrapper = ccl_chromium_indexeddb.WrappedIndexDB(filepath, blobpath)

    extracted_values = []

    for db_info in wrapper.database_ids:
        # Skip databases without a valid dbid_no
        if db_info.dbid_no is None:
            continue

        db = wrapper[db_info.dbid_no]

        for obj_store_name in db.object_store_names:
            # Skip empty object stores
            if obj_store_name is None:
                continue
            if obj_store_name in TEAMS_DB_OBJECT_STORES or filter_db_results is False:
                obj_store = db[obj_store_name]
                records_per_object_store = 0
                for record in obj_store.iterate_records(errors_to_stdout=True):
                    # skip empty records
                    if not hasattr(record, "value") or record.value is None:
                        continue
                    # skip records without file origin
                    if not hasattr(record, "origin_file") or record.origin_file is None:
                        continue
                    records_per_object_store += 1
                    # TODO: Fix None values
                    state = None
                    seq = None
                    extracted_values.append({
                        "key": record.key.raw_key,
                        "value": record.value,
                        "origin_file": record.origin_file,
                        "store": obj_store_name,
                        "state": state,
                        "seq": seq,
                    })
                print(
                    f"{obj_store_name} {db.name} (Records: {records_per_object_store})"
                )
    return extracted_values


def parse_localstorage(filepath: Path) -> list[dict[str, Any]]:
    local_store = ccl_chromium_localstorage.LocalStoreDb(filepath)
    extracted_values = []
    for record in local_store.iter_all_records():
        try:
            extracted_values.append(json.loads(record.value, strict=False))
        except json.decoder.JSONDecodeError:
            continue
    return extracted_values


def parse_sessionstorage(filepath: Path) -> list[dict[str, Any]]:
    session_storage = ccl_chromium_sessionstorage.SessionStoreDb(filepath)
    extracted_values = []
    for host in session_storage:
        print(host)
        # Hosts can have multiple sessions associated with them
        for session_store_values in session_storage.get_all_for_host(host).values():
            for session_store_value in session_store_values:
                # response is of type SessionStoreValue

                # Make a nice dictionary out of it
                entry = {
                    "key": host,
                    "value": session_store_value.value,
                    "guid": getattr(session_store_value, "guid", ""),
                    "leveldb_sequence_number": session_store_value.leveldb_sequence_number,
                }
                extracted_values.append(entry)
    return extracted_values


def write_results_to_json(data: list[dict[str, Any]], outputpath: Path) -> None:
    # Dump messages into a json file
    try:
        with open(outputpath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, default=str, ensure_ascii=False)
    except OSError as e:
        print(e)
