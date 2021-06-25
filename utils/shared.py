import json

def write_results_to_json(data, outputpath):
    # Dump messages into a json file
    try:
        with open(outputpath, 'w') as f:
            json.dump(data, f)
    except EnvironmentError as e:
        print(e)