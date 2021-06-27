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
        print("***** Processing Database *****")
        print(f"database number: {db.db_number} database name: {db.name} database origin: {db.origin}")
        print("*** Processing Object Stores ***")
        for object_store_name in db.object_store_names:
            object_store = db[object_store_name]
            print(f"object stored id: {object_store.object_store_id} object store name: {object_store.name}")
            try:
                for record in object_store.iterate_records():
                    # TODO fix origin_file it should be set the ldb or manifest file
                    extracted_values.append(
                        {'database': db.name, 'store': object_store.name, 'value': record.value, 'origin_file': db.origin})
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