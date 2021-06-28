import json
from datetime import datetime
from pathlib import Path

import pyfiglet
import argparse

from bs4 import BeautifulSoup

import shared

MESSAGE_TYPES = {
    'message': {'creator', 'conversationId', 'content', 'composetime', 'originalarrivaltime',
                'clientArrivalTime', 'isFromMe', 'createdTime', 'clientmessageid', 'contenttype', 'messagetype',
                'version', 'messageKind', 'properties', 'attachments'},
    'contact': {'displayName', 'mri', 'email', 'userPrincipalName'},
    'conversation': {'version', 'members', 'clientUpdateTime', 'id', 'threadProperties', 'type'}
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
    converted_time_datetime = datetime.utcfromtimestamp(int(content_utf8_encoded) / 1000)
    converted_time_string = converted_time_datetime.strftime('%Y-%m-%dT%H:%M:%S.%f')

    return str(converted_time_string)


def extract_fields(record, keys):
    keys_by_message_type = MESSAGE_TYPES[keys]
    extracted_record = {key: record[key] for key in record.keys() & keys_by_message_type}
    return extracted_record


def parse_contacts(contacts):
    cleaned = []
    for contact in contacts:
        value = contact['value']
        x = extract_fields(value, 'contact')
        x['origin_file'] = contact['origin_file']
        x['record_type'] = 'contact'
        cleaned.append(x)

    # Deduplicate based on mri - should be unique anyway
    cleaned = deduplicate(cleaned, 'mri')

    return cleaned


def parse_reply_chain(reply_chains):
    cleaned = []
    for reply_chain in reply_chains:
        value = reply_chain['value']
        message = value['messages']
        for key, value in message.items():
            # parse as a normal chat message

            x = extract_fields(value, 'message')
            x['origin_file'] = reply_chain['origin_file']
            # Files send without any description will be of type text
            if x['messagetype'] == 'RichText/Html' or x['messagetype'] == 'Text':
                # Get the call logs
                if 'call-log' in x['properties']:
                    # call logs are string escaped
                    x['properties']['call-log'] = json.loads(value['properties']['call-log'])
                    x['record_type'] = 'call'
                # Get the reactions from the chat
                elif 'activity' in x['properties']:
                    # reactionInChat are for personal conversations, reactions are for posts or comments
                    if x['properties']['activity']['activityType'] == 'reactionInChat' or 'reaction':
                        x['record_type'] = 'reaction'
                # normal message, posts, file transfers
                else:
                    x['content'] = strip_html_tags(x['content'])
                    x['record_type'] = 'message'

                    # handle string escaped json arrays within properties
                    if 'links' in x['properties']:
                        x['properties']['links'] = json.loads(x['properties']['links'])
                    if 'files' in x['properties']:
                        x['properties']['files'] = json.loads(x['properties']['files'])
                # convert the timestamps
                x['createdTime'] = convert_time_stamps(x['createdTime'])
                x['version'] = convert_time_stamps(x['version'])
                # manually construct the cachedDeduplicationKey, because not every replychain appears to have it
                x['cachedDeduplicationKey'] = str(x['creator']+x['clientmessageid'])
                cleaned.append(x)
            # Other types include ThreadActivity/TopicUpdate and ThreadActivity/AddMember
            # -> ThreadActivity/TopicUpdate occurs for meeting updates
            # -> ThreadActivity/AddMember occurs when someone gets added to a chat

    # Deduplicate
    cleaned = deduplicate(cleaned, 'cachedDeduplicationKey')
    return cleaned


def parse_conversations(conversations):
    cleaned = []
    for conversation in conversations:
        try:
            value = conversation['value']
            x = extract_fields(value, 'conversation')
            # Include file origin for records
            x['origin_file'] = conversation['origin_file']
            if x['type'] == 'Meeting':
                # assign the type for further processing as the object store might not be sufficient
                if 'threadProperties' in x:
                    if 'meeting' in x['threadProperties']:
                        x['threadProperties']['meeting'] = json.loads(x['threadProperties']['meeting'])
                        x['record_type'] = 'meeting'
                        cleaned.append(x)
        except UnicodeDecodeError:
            print("Could not decode meeting.")
        # Other types include Message, Chat, Space
    return cleaned


def parse_records(records):
    parsed_records = []

    # Parse the records based on the store they are in. Some records, such as meetings appear in multiple store.
    # The most appropriate one was used in this case.

    # parse contacts
    contacts = [d for d in records if d['store'] == 'people']
    parsed_records += parse_contacts(contacts)

    # parse text messages, posts, call logs, file transfers
    reply_chains = [d for d in records if d['store'] == 'replychains']
    parsed_records += parse_reply_chain(reply_chains)

    # parse meetings
    conversations = [d for d in records if d['store'] == 'conversations']
    parsed_records += parse_conversations(conversations)

    return parsed_records


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

    extracted_values = shared.parse_db(filepath)

    # extracted_values = shared.parse_json()

    # parse records
    parsed_records = parse_records(extracted_values)

    # write the output to a json file
    shared.write_results_to_json(parsed_records, output_path)

def run(args):
    process_db(args.filepath, args.outputpath)

def parse_cmdline():
    description = 'Forensics.im Xtract Tool'
    parser = argparse.ArgumentParser(description=description)
    required_group = parser.add_argument_group('required arguments')
    required_group.add_argument('--filepath', required=True, help='File path to the IndexedDB.')
    required_group.add_argument('--outputpath', required=True, help='File path to the procesed output.')
    args = parser.parse_args()
    return args

def cli():
    header = pyfiglet.figlet_format("Forensics.im Xtract Tool")
    print(header)
    args = parse_cmdline()
    run(args)


if __name__ == '__main__':
    cli()
