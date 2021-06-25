from datetime import datetime
from pathlib import Path

import click
import pyfiglet
from bs4 import BeautifulSoup

import shared

MESSAGE_TYPES = {
    'message': {'creator','conversationId','content', 'composetime', 'originalarrivaltime','clientArrivalTime','cachedDeduplicationKey', 'isFromMe', 'createdTime', 'clientmessageid','contenttype', 'messagetype', 'version', 'messageKind', 'properties', 'attachments'},
    'contact': {'displayName', 'mri', 'email', 'userPrincipalName'}
}

IDENTIFIER = {
    'message': {'identifier': {'messagetype': 'RichText/Html'}},
    'meeting': {'identifier': {'messagetype': 'ThreadActivity/TopicUpdate'}}
}


def strip_html_tags(value):
    try:
        # Get the text of any embedded html, such as divs, a href links
        soup = BeautifulSoup(value, features="html.parser")
        text = soup.get_text()
        return text
    except:
        return value





def convert_time_stamps(content_utf8_encoded):
    # timestamp appear in epoch format with milliseconds alias currentmillis
    # Convert data to neat timestamp
    delete_time_datetime = datetime.utcfromtimestamp(int(content_utf8_encoded) / 1000)
    delete_time_string = delete_time_datetime.strftime('%Y-%m-%dT%H:%M:%S.%f')

    return str(delete_time_string)

def parse_text_message(messages):
    # messages.sort(key=lambda date: datetime.strptime(date['composetime'][:19], "%Y-%m-%dT%H:%M:%S"))

    # Print the text messages
    for m in messages:
        print(m['value'])
        # print(f"Compose Time: {m['composetime'][:19]} - User: {m['imdisplayname']} - Message: {m['content']}")


def extract_fields(record, keys):
    keys_by_message_type = MESSAGE_TYPES[keys]
    extracted_record = {key: record[key] for key in record.keys() & keys_by_message_type}
    return extracted_record

def parse_contacts(contacts):
    cleaned = []
    for contact in contacts:
        value = contact['value']
        x = extract_fields(value, 'contact')
        cleaned.append(x)

    # Deduplicate based on mri
    cleaned = deduplicate(cleaned, 'mri')
    for c in cleaned:
        print(c)

def parse_conversation(conversations):
    cleaned = []
    for conversation in conversations:
        value = conversation['value']
        message = value['messages']
        for key, value in message.items():

            x = extract_fields(value, 'message')
            x['content'] = strip_html_tags(x['content'])
            # convert the timestamps
            x['createdTime'] = convert_time_stamps(x['createdTime'])
            x['version'] = convert_time_stamps(x['version'])

            cleaned.append(x)


    # Deduplicate
    cleaned = deduplicate(cleaned, 'cachedDeduplicationKey')
    # Sort by Date
    cleaned.sort(key=lambda date: datetime.strptime(date['composetime'][:19], "%Y-%m-%dT%H:%M:%S"))

    for c in cleaned:
        print(c)

def parse_calendar_events(events):
    cleaned = []
    for event in events:
        value = event['value']
        print(value)


    for c in cleaned:
        print(c)

def parse_records(records):
    parsed_records = []

    # messages = [d for d in records if d['store'] == 'messages']
    # parse_text_message(messages)
    # parse contacts
    # contacts = [d for d in records if d['store'] == 'people']
    # parse_contacts(contacts)
    # parse text messages
    reply_chains = [d for d in records if d['store'] == 'replychains']
    parse_conversation(reply_chains)
    # notifications = [d for d in records if d['store'] == 'notifications']
    # calendarevents = [d for d in records if d['store'] == 'CalendarEvents']
    # parse_calendar_events(calendarevents)
    # replychains = [d for d in records if d['store'] == 'replychains']
    # memberslru = [d for d in records if d['store'] == 'members_lru']


def deduplicate(records, key):
    distinct_records = [i for n, i in enumerate(records) if
                    i.get(key) not in [y.get(key) for y in
                                                            records[n + 1:]]]
    return distinct_records


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
    # TODO Switch back once done
    # extracted_values = shared.parse_db(filepath)

    extracted_values = shared.parse_json()

    # parse records
    parsed_records = parse_records(extracted_values)

    # deduplicate entries
    # parsed_records = deduplicate(parsed_records)

    # write the output to a json file
    # shared.write_results_to_json(parsed_records, output_path)


@click.command()
@click.option('--filepath', '-f', required=True,
              default="\IndexedDB\https_teams.microsoft.com_0.indexeddb.leveldb",
              help="Relative file path to JSON with conversation data")
@click.option('--outputpath', '-o', required=True, default='teams.json',
              help="Relative file path to JSON with conversation data")
def cli(filepath, outputpath):
    header = pyfiglet.figlet_format("Forensics.im Xtract Tool")
    click.echo(header)
    process_db(filepath, outputpath)


if __name__ == '__main__':
    cli()
