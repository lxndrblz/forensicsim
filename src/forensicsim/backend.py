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

import io
import json
import os
from pathlib import Path

from chromedb import (
    ccl_blink_value_deserializer,
    ccl_chromium_indexeddb,
    ccl_chromium_localstorage,
    ccl_chromium_sessionstorage,
    ccl_leveldb,
    ccl_v8_value_deserializer,
)
from chromedb.ccl_chromium_indexeddb import (
    DatabaseMetadataType,
    ObjectStoreMetadataType,
)

TEAMS_DB_OBJECT_STORES = ["replychains", "conversations", "people", "buddylist"]

"""
The following code is heavily adopted from the RawLevelDb and IndexedDB processing proposed by CCL Group

https://github.com/cclgroupltd/ccl_chrome_indexeddb/blob/35b6a9efba1078cf339f9e64d2796b1f5f7c556f/ccl_chromium_indexeddb.py

It uses an optimized enumeration approach for processing the metadata, which makes the original IndexedDB super slow.

Additionally, it has a flag to filter for datastores, which are interesting for us.
"""


class FastIndexedDB:
    def __init__(self, leveldb_dir: os.PathLike):
        self._db = ccl_leveldb.RawLevelDb(leveldb_dir)
        self._fetched_records = []
        self.global_metadata = None
        self.database_metadata = None
        self.object_store_meta = None
        self.fetch_data()

    def fetch_data(self):
        global_metadata_raw = {}

        database_metadata_raw = {}
        objectstore_metadata_raw = {}

        self._fetched_records = []
        # Fetch the records only once
        for record in self._db.iterate_records_raw():
            self._fetched_records.append(record)

        for record in self._fetched_records:
            # Global Metadata
            if (
                record.key.startswith(b"\x00\x00\x00\x00")
                and record.state == ccl_leveldb.KeyState.Live
            ) and (
                record.key not in global_metadata_raw
                or global_metadata_raw[record.key].seq < record.seq
            ):
                global_metadata_raw[record.key] = record

        # Convert the raw metadata to a nice GlobalMetadata Object
        global_metadata = ccl_chromium_indexeddb.GlobalMetadata(global_metadata_raw)

        # Loop through the database IDs
        for db_id in global_metadata.db_ids:
            if db_id.dbid_no == None:
                continue
            # if db_id.dbid_no > 0x7f:
            #     raise NotImplementedError("there could be this many dbs, but I don't support it yet")
            #
            # # Database keys end with 0
            # prefix_database = bytes([0, db_id.dbid_no, 0, 0])
            #
            # # Objetstore keys end with 50
            # prefix_objectstore = bytes([0, db_id.dbid_no, 0, 0, 50])

            prefix_database = IndexedDb.make_prefix(db_id.dbid_no, 0, 0)
            prefix_objectstore = IndexedDb.make_prefix(db_id.dbid_no, 0, 0, [50])

            for record in reversed(self._fetched_records):
                if (
                    record.key.startswith(prefix_database)
                    and record.state == ccl_leveldb.KeyState.Live
                ):
                    # we only want live keys and the newest version thereof (highest seq)
                    meta_type = record.key[len(prefix_database)]
                    old_version = database_metadata_raw.get((db_id.dbid_no, meta_type))
                    if old_version is None or old_version.seq < record.seq:
                        database_metadata_raw[(db_id.dbid_no, meta_type)] = record
                if (
                    record.key.startswith(prefix_objectstore)
                    and record.state == ccl_leveldb.KeyState.Live
                ):
                    # we only want live keys and the newest version thereof (highest seq)
                    try:
                        (
                            objstore_id,
                            varint_raw,
                        ) = ccl_chromium_indexeddb.custom_le_varint_from_bytes(
                            record.key[len(prefix_objectstore) :]
                        )
                    except TypeError:
                        continue

                    meta_type = record.key[len(prefix_objectstore) + len(varint_raw)]

                    old_version = objectstore_metadata_raw.get((
                        db_id.dbid_no,
                        objstore_id,
                        meta_type,
                    ))

                    if old_version is None or old_version.seq < record.seq:
                        objectstore_metadata_raw[
                            (db_id.dbid_no, objstore_id, meta_type)
                        ] = record

        self.global_metadata = global_metadata
        self.database_metadata = ccl_chromium_indexeddb.DatabaseMetadata(
            database_metadata_raw
        )
        self.object_store_meta = ccl_chromium_indexeddb.ObjectStoreMetadata(
            objectstore_metadata_raw
        )

    def get_database_metadata(self, db_id: int, meta_type: DatabaseMetadataType):
        return self.database_metadata.get_meta(db_id, meta_type)

    def get_object_store_metadata(
        self, db_id: int, obj_store_id: int, meta_type: ObjectStoreMetadataType
    ):
        return self.object_store_meta.get_meta(db_id, obj_store_id, meta_type)

    def iterate_records(self, do_not_filter=False):
        blink_deserializer = ccl_blink_value_deserializer.BlinkV8Deserializer()
        # Loop through the databases and object stores based on their ids
        for global_id in self.global_metadata.db_ids:
            # print(f"Processing database: {global_id.name}")
            if global_id.dbid_no == None:
                print(f"WARNING: Skipping database {global_id.name}")
                continue

            for object_store_id in range(
                1,
                self.database_metadata.get_meta(
                    global_id.dbid_no, DatabaseMetadataType.MaximumObjectStoreId
                )
                + 1,
            ):
                datastore = self.object_store_meta.get_meta(
                    global_id.dbid_no,
                    object_store_id,
                    ObjectStoreMetadataType.StoreName,
                )

                # print(f"\t Processing object store: {datastore}")
                records_per_object_store = 0
                if datastore in TEAMS_DB_OBJECT_STORES or do_not_filter:
                    prefix = bytes([0, global_id.dbid_no, object_store_id, 1])
                    for record in self._fetched_records:
                        if record.key.startswith(prefix):
                            records_per_object_store += 1
                            # Skip records with empty values as these cant properly decoded
                            if record.value == b"":
                                continue
                            (
                                _value_version,
                                varint_raw,
                            ) = ccl_chromium_indexeddb.custom_le_varint_from_bytes(
                                record.value
                            )
                            val_idx = len(varint_raw)
                            # read the blink envelope
                            blink_type_tag = record.value[val_idx]
                            if blink_type_tag != 0xFF:
                                print("Blink type tag not present")
                            val_idx += 1

                            (
                                _,
                                varint_raw,
                            ) = ccl_chromium_indexeddb.custom_le_varint_from_bytes(
                                record.value[val_idx:]
                            )

                            val_idx += len(varint_raw)

                            # read the raw value of the record.
                            obj_raw = io.BytesIO(record.value[val_idx:])
                            try:
                                # Initialize deserializer and try deserialization.
                                deserializer = ccl_v8_value_deserializer.Deserializer(
                                    obj_raw,
                                    host_object_delegate=blink_deserializer.read,
                                )
                                value = deserializer.read()
                                yield {
                                    "key": record.key,
                                    "value": value,
                                    "origin_file": record.origin_file,
                                    "store": datastore,
                                    "state": record.state,
                                    "seq": record.seq,
                                }
                            except Exception:
                                # TODO Some proper error handling wouldn't hurt
                                continue
                # print(f"{datastore} {global_id.name} {records_per_object_store}")


def parse_db(filepath, do_not_filter=False):
    # Open raw access to a LevelDB and deserialize the records.
    db = FastIndexedDB(filepath)
    extracted_values = []
    for record in db.iterate_records(do_not_filter):
        extracted_values.append(record)
    return extracted_values


def parse_localstorage(filepath):
    local_store = ccl_chromium_localstorage.LocalStoreDb(filepath)
    extracted_values = []
    for record in local_store.iter_all_records():
        try:
            extracted_values.append(json.loads(record.value, strict=False))
        except json.decoder.JSONDecodeError:
            continue
    return extracted_values


def parse_sessionstorage(filepath):
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
                    "guid": session_store_value.guid,
                    "leveldb_sequence_number": session_store_value.leveldb_sequence_number,
                }
                extracted_values.append(entry)
    return extracted_values


def write_results_to_json(data, outputpath):
    # Dump messages into a json file
    try:
        with open(outputpath, "w", encoding="utf-8") as f:
            json.dump(
                data, f, indent=4, sort_keys=True, default=str, ensure_ascii=False
            )
    except OSError as e:
        print(e)


def parse_json():
    # read data from a file. This is only for testing purpose.
    try:
        with Path("teams.json").open() as json_file:
            return json.load(json_file)
    except OSError as e:
        print(e)
