from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

from bs4 import BeautifulSoup
import click
from dataclasses import dataclass, fields, field
from dataclasses_json import LetterCase, dataclass_json

from shared import parse_db, write_results_to_json
from consts import XTRACT_HEADER


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass(init=False)
class Meeting:
    client_update_time: str | None = None
    cached_deduplication_key: str | None = None
    id: str | None = None
    members: list[dict] | None = None
    thread_properties: dict[str, Any] = field(default_factory=dict)
    type: str | None = None
    version: float | None = None

    record_type: str | None = "meeting"

    def __init__(self, **kwargs):
        # allow to pass optional kwargs
        # https://stackoverflow.com/a/54678706/5755604
        names = set([f.name for f in fields(self)])
        for k, v in kwargs.items():
            if k in names:
                setattr(self, k, v)

    # def __post_init__(self):
    #     self.thread_properties["meeting"] = decode_and_loads(self.thread_properties.get("meeting",b""))

    def __eq__(self, other):
        return self.cached_deduplication_key == other.cachedDeduplicationKey

    def __hash__(self):
        return hash(("cachedDeduplicationKey", self.cached_deduplication_key))


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass(init=False)
class Message:
    attachments: list[Any] = field(default_factory=list)
    client_arrival_time: str | None = None
    clientmessageid: str | None = None
    clientmessageid: str | None = None
    composetime: str | None = None
    content: str | None = None
    contenttype: str | None = None
    created_time: str | None = None
    creator: str | None = None
    is_from_me: bool | None = None
    message_kind: str | None = None
    messagetype: str | None = None
    originalarrivaltime: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    version: str | None = None

    record_type: str | None = "message"

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


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass(init=False)
class Contact:
    display_name: str | None = None
    email: str | None = None
    mri: str | None = None
    user_principal_name: str | None = None

    origin_file: str | None = None
    record_type: str = "contact"

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

    def __lt__(self, other):
        return self.mri < other.mri


def map_updated_teams_keys(value):
    # Seems like Microsoft discovered duck typing
    # set the new keys to the old values too
    # value["composetime"] = convert_time_stamps(value["id"])
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


def decode_timestamp(content_utf8_encoded):
    # timestamp appear in epoch format with milliseconds alias currentmillis
    # Convert data to neat timestamp
    converted_time_datetime = datetime.utcfromtimestamp(
        int(content_utf8_encoded) / 1000
    )
    converted_time_string = converted_time_datetime.strftime("%Y-%m-%dT%H:%M:%S.%f")

    return str(converted_time_string)


def decode_dict(properties):
    if isinstance(properties, bytes):
        soup = BeautifulSoup(properties, features="html.parser")
        properties = properties.decode(soup.original_encoding)
    return json.loads(properties, strict=False)


def _parse_people(people: list[dict]) -> set[Contact]:
    parsed_people = set()
    for p in people:
        kwargs = p.get("value", {}) | {"origin_file": p.get("origin_file")}
        parsed_people.add(Contact(**kwargs))
    return parsed_people


def _parse_buddies(buddies: list[dict]) -> set[Contact]:
    parsed_buddies = set()
    for b in buddies:
        buddies_of_b = b.get("value", {}).get("buddies", [])
        for b_of_b in buddies_of_b:
            kwargs = {"origin_file": b.get("origin_file")} | b_of_b
            parsed_buddies.add(Contact(**kwargs))
    return parsed_buddies


def _parse_conversations(conversations: list[dict]) -> set[Meeting]:
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
            # TODO: Move into dataclass?
            kwargs["threadProperties"]["meeting"] = decode_dict(
                kwargs["threadProperties"]["meeting"]
            )
            cleaned_conversations.add(Meeting(**kwargs))

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
                                x["properties"]["call-log"] = decode_dict(
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
                                    x["properties"]["links"] = decode_dict(
                                        x["properties"]["links"]
                                    )
                                if "files" in x["properties"]:
                                    x["properties"]["files"] = decode_dict(
                                        x["properties"]["files"]
                                    )
                            # convert the timestamps
                            x["createdTime"] = decode_timestamp(x["createdTime"])
                            x["version"] = decode_timestamp(x["version"])
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

    for r in records:
        store = r.get("store", "other")
        if store == "people":
            people.append(r)
        elif store == "buddylist":
            buddies.append(r)
        elif r.get("store") == "replychains":
            reply_chains.append(r)
        elif store == "conversations":
            conversations.append(r)

    # sort within groups i.e., Contacts, Meetings, Conversations
    parsed_records = (
        sorted(_parse_people(people) | _parse_buddies(buddies))
        + sorted(_parse_reply_chains(reply_chains))
        + sorted(_parse_conversations(conversations))
    )
    return [r.to_dict() for r in parsed_records]


def process_db(input_path: Path, output_path: Path):
    if not input_path.parts[-1].endswith(".leveldb"):
        raise ValueError(f"Expected a leveldb folder. Path: {input_path}")

    extracted_values = parse_db(input_path)
    parsed_records = parse_records(extracted_values)
    write_results_to_json(parsed_records, output_path)


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
    click.echo(XTRACT_HEADER)
    process_db(filepath, outputpath)
    sys.exit(0)


if __name__ == "__main__":
    process_cmd()
