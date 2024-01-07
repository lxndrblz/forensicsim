from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

from bs4 import BeautifulSoup
import click
from dataclasses import dataclass, field
from dataclasses_json import LetterCase, dataclass_json, Undefined

from shared import parse_db, write_results_to_json
from consts import XTRACT_HEADER


@dataclass_json(letter_case=LetterCase.CAMEL, undefined=Undefined.EXCLUDE)
@dataclass()
class Meeting:
    client_update_time: str | None = None
    cached_deduplication_key: str | None = None
    id: str | None = None
    members: list[dict] | None = None
    thread_properties: dict[str, Any] = field(default_factory=dict)
    type: str | None = None
    version: float | None = None

    record_type: str | None = "meeting"

    def __eq__(self, other):
        return self.cached_deduplication_key == other.cachedDeduplicationKey

    def __hash__(self):
        return hash(("cachedDeduplicationKey", self.cached_deduplication_key))

    def __lt__(self, other):
        return self.cached_deduplication_key < other.cached_deduplication_key


@dataclass_json(letter_case=LetterCase.CAMEL, undefined=Undefined.EXCLUDE)
@dataclass()
class Message:
    attachments: list[Any] = field(default_factory=list)
    cached_deduplication_key: str | None = None
    client_arrival_time: str | None = None
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

    origin_file: str | None = None
    record_type: str | None = "message"

    def __post_init__(self):
        if self.cached_deduplication_key is None:
            self.cached_deduplication_key = self.creator + self.clientmessageid

    def __eq__(self, other):
        return (
            self.creator == other.creator
            and self.clientmessageid == other.clientmessageid
        )

    def __hash__(self):
        return hash(("cachedDeduplicationKey", self.cached_deduplication_key))

    def __lt__(self, other):
        return self.cached_deduplication_key < other.cached_deduplication_key


@dataclass_json(letter_case=LetterCase.CAMEL, undefined=Undefined.EXCLUDE)
@dataclass()
class Contact:
    display_name: str | None = None
    email: str | None = None
    mri: str | None = None
    user_principal_name: str | None = None

    origin_file: str | None = None
    record_type: str = "contact"

    def __eq__(self, other):
        return self.mri == other.mri

    def __hash__(self):
        return hash(("mri", self.mri))

    def __lt__(self, other):
        return self.mri < other.mri


LUT_KEYS_MSTEAMS_2_0 = {
    "messageMap": "messages",
    "id": "created_time",
    "isSentByCurrentUser": "isFromMe",
    "originalArrivalTime": "originalarrivaltime",
    "clientMessageId": "clientmessageid",
    "contentType": "contenttype",
    "messageType": "messagetype",
}


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
        parsed_people.add(Contact.from_dict(kwargs))
    return parsed_people


def _parse_buddies(buddies: list[dict]) -> set[Contact]:
    parsed_buddies = set()
    for b in buddies:
        buddies_of_b = b.get("value", {}).get("buddies", [])
        for b_of_b in buddies_of_b:
            kwargs = {"origin_file": b.get("origin_file")} | b_of_b
            parsed_buddies.add(Contact.from_dict(kwargs))
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
            kwargs["threadProperties"]["meeting"] = decode_dict(
                kwargs["threadProperties"]["meeting"]
            )
            cleaned_conversations.add(Meeting.from_dict(kwargs))

    return cleaned_conversations


def _parse_reply_chains(reply_chains: list[dict]) -> set[Message]:
    cleaned_reply_chains = set()

    for rc in reply_chains:
        kwargs = rc.get("value", {}) | {"origin_file": rc.get("origin_file")}

        # Reassign new keys to old identifiers
        keys = [LUT_KEYS_MSTEAMS_2_0.get(k, k) for k in kwargs.keys()]
        kwargs.update(zip(keys, kwargs.values()))

        for message_values in kwargs.get("messages", {}).values():
            message_properties = message_values.get("properties", {})
            # TODO: Required to check fo "RichText/Html" "Text"?

            # general
            if "links" in message_values:
                message_values["links"] = decode_dict(message_values["links"])
            if "files" in message_values:
                message_values["files"] = decode_dict(message_values["files"])
            if "content" in message_values:
                message_values["content"] = strip_html_tags(message_values["content"])

            # specific
            if "call-log" in message_properties:
                message_values["record_type"] = "call"
                message_properties["call-log"] = decode_dict(
                    message_properties["call-log"]
                )
            if "activity" in message_properties:
                # TODO: required to check for "reactionInChat" or "reaction"?
                message_values["record_type"] = "reaction"

            cleaned_reply_chains.add(Message.from_dict(message_values))
    return cleaned_reply_chains


def parse_records(records: list[dict]) -> list[dict]:
    people, buddies, reply_chains, conversations = [], [], [], []

    for r in records:
        store = r.get("store", "other")
        if store == "people":
            people.append(r)
        elif store == "buddylist":
            buddies.append(r)
        elif store == "replychains":
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
