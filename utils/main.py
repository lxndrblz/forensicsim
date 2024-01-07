from typing import Any
import json
from datetime import datetime
from pathlib import Path

from consts import XTRACT_HEADER
from bs4 import BeautifulSoup
import click

import shared
import sys

from dataclasses import dataclass, fields, asdict, field

MESSAGE_TYPES = {
    "messages": {
        "creator",
        "conversationId",
        "content",
        "composetime",
        "originalarrivaltime",
        "clientArrivalTime",
        "isFromMe",
        "createdTime",
        "clientmessageid",
        "contenttype",
        "messagetype",
        "version",
        "messageKind",
        "properties",
        "attachments",
    },
    "messageMap": {
        "creator",
        "conversationId",
        "content",
        "id",
        "originalArrivalTime",
        "clientArrivalTime",
        "isSentByCurrentUser",
        "clientMessageId",
        "contentType",
        "messageType",
        "version",
        "properties",
    },
}

# TODO: check better ways of camelcase conversion https://github.com/lidatong/dataclasses-json


@dataclass(init=False)
class Conversation:
    clientUpdateTime: str | None = None
    cachedDeduplicationKey: str | None = None
    id: str | None = None
    members: list[dict] | None = None
    record_type: str | None = None
    threadProperties: dict[str, Any] = field(default_factory=dict)
    type: str | None = None
    version: float | None = None

    def __init__(self, **kwargs):
        # allow to pass optional kwargs
        # https://stackoverflow.com/a/54678706/5755604
        names = set([f.name for f in fields(self)])
        for k, v in kwargs.items():
            if k in names:
                setattr(self, k, v)

    def __eq__(self, other):
        return self.cachedDeduplicationKey == other.cachedDeduplicationKey

    def __hash__(self):
        return hash(("cachedDeduplicationKey", self.cachedDeduplicationKey))


@dataclass(init=False)
class Message:
    attachments: list[Any] = field(default_factory=list)
    clientArrivalTime: str | None = None
    clientmessageid: str | None = None
    clientmessageid: str | None = None
    composetime: str | None = None
    content: str | None = None
    contenttype: str | None = None
    createdTime: str | None = None
    creator: str | None = None
    isFromMe: bool | None = None
    messageKind: str | None = None
    messagetype: str | None = None
    originalarrivaltime: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    record_type: str | None = None
    version: str | None = None

    def __init__(self, **kwargs):
        # allow to pass optional kwargs
        # https://stackoverflow.com/a/54678706/5755604
        names = set([f.name for f in fields(self)])
        for k, v in kwargs.items():
            if k in names:
                setattr(self, k, v)

    def __eq__(self, other):
        return (
            self.creator == other.creator
            and self.clientmessageid == other.clientmessageid
        )

    def __hash__(self):
        return hash(("creator", self.creator, "clientmessageid", self.clientmessageid))


@dataclass(init=False)
class Contact:
    displayName: str | None = None
    email: str | None = None
    mri: str | None = None
    origin_file: str | None = None
    record_type: str = "contact"
    userPrincipalName: str | None = None

    def __init__(self, **kwargs):
        # allow to pass optional kwargs
        names = set([f.name for f in fields(self)])
        for k, v in kwargs.items():
            if k in names:
                setattr(self, k, v)

    def __eq__(self, other):
        return self.mri == other.mri

    def __hash__(self):
        return hash(("mri", self.mri))


def map_updated_teams_keys(value):
    # Seems like Microsoft discovered duck typing
    # set the new keys to the old values too
    value["composetime"] = convert_time_stamps(value["id"])
    value["createdTime"] = value["id"]
    value["isFromMe"] = value["isSentByCurrentUser"]
    value["originalarrivaltime"] = value["originalArrivalTime"]
    value["clientmessageid"] = value["clientMessageId"]
    value["contenttype"] = value["contentType"]
    value["messagetype"] = value["messageType"]
    return value


def strip_html_tags(value):
    # Get the text of any embedded html, such as divs, a href links
    soup = BeautifulSoup(value, features="html.parser")
    return soup.get_text()


def convert_time_stamps(content_utf8_encoded):
    # timestamp appear in epoch format with milliseconds alias currentmillis
    # Convert data to neat timestamp
    converted_time_datetime = datetime.utcfromtimestamp(
        int(content_utf8_encoded) / 1000
    )
    converted_time_string = converted_time_datetime.strftime("%Y-%m-%dT%H:%M:%S.%f")

    return str(converted_time_string)


def extract_fields(record, keys):
    keys_by_message_type = MESSAGE_TYPES[keys]
    extracted_record = {
        key: record[key] for key in record.keys() & keys_by_message_type
    }
    return extracted_record


def decode_and_loads(properties):
    if isinstance(properties, bytes):
        soup = BeautifulSoup(properties, features="html.parser")
        properties = properties.decode(soup.original_encoding)
    return json.loads(properties)


def _parse_people(people: list[dict]) -> set[Contact]:
    parsed_people = set()
    for p in people:
        kwargs = p.get("value", {}) | {"origin_file": p.get("origin_file")}
        parsed_people.add(Contact(**kwargs))
    return parsed_people


def _parse_buddies(buddies: list[dict]) -> set[Contact]:
    parsed_buddies = set()
    for b in buddies:
        kwargs = b.get("value", {}).get("buddies", {}) | {
            "origin_file": b.get("origin_file")
        }
        parsed_buddies.add(Contact(**kwargs))
    return parsed_buddies


def _parse_conversations(conversations: list[dict]) -> set[Conversation]:
    cleaned_conversations = set()
    for c in conversations:
        last_message = c.get("value", {}).get("lastMessage", {})

        kwargs = c.get("value", {}) | {
            "cachedDeduplicationKey": last_message.get("cachedDeduplicationKey"),
            "origin_file": c.get("origin_file"),
            "threadProperties": c.get("threadProperties"),
            "type": c.get("type"),
        }

        if kwargs["type"] == "Meeting" and "meeting" in kwargs["threadProperties"]:
            kwargs["threadProperties"]["meeting"] = decode_and_loads(
                kwargs["threadProperties"]["meeting"]
            )
            kwargs["record_type"] = "meeting"
            cleaned_conversations.add(Conversation(**kwargs))

    return cleaned_conversations


def _parse_reply_chains(reply_chains: list[dict]) -> set[Message]:
    cleaned_reply_chains = set()
    return cleaned_reply_chains


def parse_reply_chain(reply_chains):
    cleaned = []
    for reply_chain in reply_chains:
        value = reply_chain["value"]
        # The way of accessing a the nested messages is different depending on the teams version -> check for both
        message_keys = ["messageMap", "messages"]
        for message_key in message_keys:
            if message_key in value:
                message = value[message_key]
                for key, value in message.items():
                    # parse as a normal chat message
                    try:
                        x = extract_fields(value, message_key)
                        # reassign the new keys to the old identifiers
                        if message_key == "messageMap":
                            x = map_updated_teams_keys(x)
                        x["origin_file"] = reply_chain["origin_file"]
                        # Files send without any description will be of type text
                        # Newer version uses duck typed key
                        if "messagetype" in x and (
                            x["messagetype"] == "RichText/Html"
                            or x["messagetype"] == "Text"
                        ):
                            # Get the call logs

                            if "call-log" in x["properties"]:
                                # call logs are string escaped
                                x["properties"]["call-log"] = decode_and_loads(
                                    value["properties"]["call-log"]
                                )
                                x["record_type"] = "call"
                            # Get the reactions from the chat
                            elif "activity" in x["properties"]:
                                # reactionInChat are for personal conversations, reactions are for posts or comments
                                if (
                                    x["properties"]["activity"]["activityType"]
                                    == "reactionInChat"
                                    or x["properties"]["activity"]["activityType"]
                                    == "reaction"
                                ):
                                    x["record_type"] = "reaction"
                            # normal message, posts, file transfers
                            else:
                                x["content"] = strip_html_tags(x["content"])

                                x["record_type"] = "message"

                                # handle string escaped json arrays within properties
                                if "links" in x["properties"]:
                                    x["properties"]["links"] = decode_and_loads(
                                        x["properties"]["links"]
                                    )
                                if "files" in x["properties"]:
                                    x["properties"]["files"] = decode_and_loads(
                                        x["properties"]["files"]
                                    )
                            # convert the timestamps
                            x["createdTime"] = convert_time_stamps(x["createdTime"])
                            x["version"] = convert_time_stamps(x["version"])
                            # manually construct the cachedDeduplicationKey, because not every replychain appears to have this key.
                            # cachedDeduplicationKey look like 8:orgid:54dd27a7-fbb0-4bf0-8208-a4b31a578a3f6691174965251523000
                            # They are composed of the:
                            # -> creator 8:orgid:54dd27a7-fbb0-4bf0-8208-a4b31a578a3f
                            # -> clientmessageid 6691174965251523000
                            if (
                                x["creator"] is not None
                                and x["clientmessageid"] is not None
                                and "record_type" in x
                            ):
                                x["cachedDeduplicationKey"] = str(
                                    x["creator"] + x["clientmessageid"]
                                )
                                cleaned.append(x)
                        # Other types include ThreadActivity/TopicUpdate and ThreadActivity/AddMember
                        # -> ThreadActivity/TopicUpdate occurs for meeting updates
                        # -> ThreadActivity/AddMember occurs when someone gets added to a chat
                    except UnicodeDecodeError or KeyError or NameError as e:
                        print(
                            "Could not decode the following item in the reply chain (output is not deduplicated)."
                        )
                        print("\t ", value)

    # # Deduplicate based on cachedDeduplicationKey, as messages appear often multiple times within
    # cleaned = deduplicate(cleaned, "cachedDeduplicationKey")
    return cleaned


def parse_records(records: list[dict]) -> list[dict]:
    people, buddies, reply_chains, conversations = [], [], [], []

    with click.progressbar(
        records, label="Filtering for people/buddylist/replychains/conversations"
    ) as record_bar:
        for r in record_bar:
            if r.get("store") == "people":
                people.append(r)
            elif r.get("store") == "buddylist":
                buddies.append(r)
            # elif r.get("store") == "replychains":
            #     reply_chains.append(r)
            elif r.get("store") == "conversations":
                conversations.append(r)

    parsed_records = [
        *_parse_people(people),
        *_parse_buddies(buddies),
        *_parse_reply_chains(reply_chains),
        *_parse_conversations(conversations),
    ]

    return [asdict(r) for r in parsed_records]


def process_db(input_path: Path, output_path: Path):
    if not input_path.is_file() or input_path.suffix.lower() != "leveldb":
        raise ValueError(f"Expected a leveldb folder. Path: {input_path}")

    extracted_values = shared.parse_db(input_path)
    parsed_records = parse_records(extracted_values)
    shared.write_results_to_json(parsed_records, output_path)


@click.command()
@click.option(
    "-f",
    "--filepath",
    type=click.Path(
        exists=True, readable=True, writable=False, dir_okay=False, path_type=Path
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
    click.echo(XTRACT_HEADER)
    process_db(filepath, outputpath)
    sys.exit(0)


if __name__ == "__main__":
    process_cmd()
