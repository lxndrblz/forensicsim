import io
import json

from ccl_chrome_indexeddb import ccl_blink_value_deserializer, ccl_chromium_indexeddb, ccl_v8_value_deserializer, \
    ccl_leveldb

# db ID (second byte) is constant, store ids vary based on what we are looking for
TEAMS_DB_PREFIX = {'replychains': b'\x00\x05\x02\x01', 'conversations': b'\x00\x05\x04\x01',
                   'people': b'\x00\x05\x07\x01'}


def deserialize(db):
    # Deserializer is adopted from but uses constant database and object stores IDs rather than looping through the dbs forever.
    # https://github.com/cclgroupltd/ccl_chrome_indexeddb/blob/master/ccl_chromium_indexeddb.py

    blink_deserializer = ccl_blink_value_deserializer.BlinkV8Deserializer()

    deserialized_db = []
    for datastore in TEAMS_DB_PREFIX.keys():

        prefix = TEAMS_DB_PREFIX[datastore]
        for record in db.iterate_records_raw():
            if record.key.startswith(prefix):

                if not record.value:
                    continue
                value_version, varint_raw = ccl_chromium_indexeddb.custom_le_varint_from_bytes(record.value)
                val_idx = len(varint_raw)
                # read the blink envelope
                blink_type_tag = record.value[val_idx]
                if blink_type_tag != 0xff:
                    print("Blink type tag not present")
                val_idx += 1

                blink_version, varint_raw = ccl_chromium_indexeddb.custom_le_varint_from_bytes(record.value[val_idx:])

                val_idx += len(varint_raw)

                obj_raw = io.BytesIO(record.value[val_idx:])
                deserializer = ccl_v8_value_deserializer.Deserializer(
                    obj_raw, host_object_delegate=blink_deserializer.read)
                try:
                    value = deserializer.read()
                    deserialized_db.append({'value': value, 'origin_file': record.origin_file, 'store': datastore})
                except Exception as e:
                    pass
    return deserialized_db


def write_results_to_json(data, outputpath):
    # Dump messages into a json file
    try:
        with open(outputpath, 'w') as f:
            json.dump(data, f, indent=4, sort_keys=True, default=str)
    except EnvironmentError as e:
        print(e)


def parse_db(filepath):
    db = ccl_leveldb.RawLevelDb(filepath)
    extracted_values = deserialize(db)
    return extracted_values


def parse_json():
    try:
        with open('teams.json') as json_file:
            data = json.load(json_file)
            return data
    except EnvironmentError as e:
        print(e)
