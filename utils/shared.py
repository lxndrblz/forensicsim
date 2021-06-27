import json

from ccl_chrome_indexeddb import ccl_chromium_indexeddb

def write_results_to_json(data, outputpath):
    # Dump messages into a json file
    try:
        with open(outputpath, 'w') as f:
            json.dump(data, f, indent=4, sort_keys=True, default=str)
    except EnvironmentError as e:
        print(e)


def parse_db(filepath):
    wrapper = ccl_chromium_indexeddb.WrappedIndexDB(filepath)

    extracted_values = []
    for wrapped_db in wrapper.database_ids:
        db = wrapper[wrapped_db.dbid_no]
        for object_store_name in db.object_store_names:
            object_store = db[object_store_name]
            try:
                for record in object_store.iterate_records():
                    extracted_values.append({'database': db.name, 'store': object_store.name, 'value': record.value, 'origin_file': record.origin_file})
            except StopIteration as e:
                print(e)
    return extracted_values

def parse_json():
    try:
        with open('teams.json') as json_file:
            data = json.load(json_file)
            return data
    except EnvironmentError as e:
        print(e)