import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from bs4 import BeautifulSoup
from dataclasses_json import (
    DataClassJsonMixin,
    LetterCase,
    Undefined,
    config,
)

from forensicsim.backend import parse_db, write_results_to_json


def strip_html_tags(value):
    # Get the text of any embedded html, such as divs, a href links
    soup = BeautifulSoup(value, features="html.parser")
    return soup.get_text()


def decode_dict(properties):
    if isinstance(properties, bytes):
        soup = BeautifulSoup(properties, features="html.parser")
        properties = properties.decode(soup.original_encoding)
    if isinstance(properties, dict):
        # handle case where nested childs are dicts or list but provided with "" but have to be expanded.
        for key, value in properties.items():
            if isinstance(value, str) and value.startswith(("[", "{")):
                properties[key] = json.loads(value, strict=False)
        return properties

    return json.loads(properties, strict=False)


def decode_timestamp(content_utf8_encoded) -> datetime:
    return datetime.utcfromtimestamp(int(content_utf8_encoded) / 1000)


def encode_timestamp(timestamp) -> Optional[str]:
    if timestamp is not None:
        return timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f")
    return None


JSON_CONFIG = config(letter_case=LetterCase.CAMEL, undefined=Undefined.EXCLUDE)[
    "dataclasses_json"
]


@dataclass()
class Meeting(DataClassJsonMixin):
    dataclass_json_config = JSON_CONFIG

    client_update_time: Optional[str] = None
    cached_deduplication_key: Optional[str] = None
    id: Optional[str] = None
    members: Optional[list[dict]] = None
    thread_properties: dict[str, Any] = field(
        default_factory=dict, metadata=config(decoder=decode_dict)
    )
    type: Optional[str] = None
    version: Optional[float] = None

    record_type: Optional[str] = field(
        default="meeting", metadata=config(field_name="record_type")
    )

    def __eq__(self, other):
        return self.cached_deduplication_key == other.cachedDeduplicationKey

    def __hash__(self):
        return hash(self.cached_deduplication_key)

    def __lt__(self, other):
        return self.cached_deduplication_key < other.cached_deduplication_key


@dataclass()
class Message(DataClassJsonMixin):
    dataclass_json_config = JSON_CONFIG

    attachments: list[Any] = field(default_factory=list)
    cached_deduplication_key: Optional[str] = None
    client_arrival_time: Optional[str] = None
    clientmessageid: Optional[str] = None
    composetime: Optional[str] = None
    conversation_id: Optional[str] = None
    content: Optional[str] = field(
        default=None, metadata=config(decoder=strip_html_tags)
    )
    contenttype: Optional[str] = None
    created_time: Optional[datetime] = field(
        default=None,
        metadata=config(decoder=decode_timestamp, encoder=encode_timestamp),
    )
    creator: Optional[str] = None
    is_from_me: Optional[bool] = None
    message_kind: Optional[str] = None
    messagetype: Optional[str] = None
    originalarrivaltime: Optional[str] = None
    properties: dict[str, Any] = field(
        default_factory=dict, metadata=config(decoder=decode_dict)
    )
    version: Optional[datetime] = field(
        default=None,
        metadata=config(decoder=decode_timestamp, encoder=encode_timestamp),
    )

    origin_file: Optional[str] = field(
        default=None, metadata=config(field_name="origin_file")
    )
    record_type: str = field(
        default="message", metadata=config(field_name="record_type")
    )

    def __post_init__(self):
        if self.cached_deduplication_key is None:
            self.cached_deduplication_key = str(self.creator) + str(
                self.clientmessageid
            )
        if "call-log" in self.properties:
            self.record_type = "call"
        if "activity" in self.properties:
            self.record_type = "reaction"

    def __eq__(self, other):
        return self.cached_deduplication_key == other.cached_deduplication_key

    def __hash__(self):
        return hash(self.cached_deduplication_key)

    def __lt__(self, other):
        return self.cached_deduplication_key < other.cached_deduplication_key


@dataclass()
class Contact(DataClassJsonMixin):
    dataclass_json_config = JSON_CONFIG

    display_name: Optional[str] = None
    email: Optional[str] = None
    mri: Optional[str] = field(default=None, compare=True)
    user_principal_name: Optional[str] = None

    origin_file: Optional[str] = field(
        default=None, metadata=config(field_name="origin_file")
    )
    record_type: Optional[str] = field(
        default="contact", metadata=config(field_name="record_type")
    )

    def __eq__(self, other):
        return self.mri == other.mri

    def __hash__(self):
        return hash(self.mri)

    def __lt__(self, other):
        return self.mri < other.mri


def _parse_people(people: list[dict]) -> set[Contact]:
    parsed_people = set()
    for p in people:
        p |= {"origin_file": p.get("origin_file")}
        p |= p.get("value", {})
        parsed_people.add(Contact.from_dict(p))
    return parsed_people


def _parse_buddies(buddies: list[dict]) -> set[Contact]:
    parsed_buddies = set()
    for b in buddies:
        buddies_of_b = b.get("value", {}).get("buddies", [])
        for b_of_b in buddies_of_b:
            b_of_b |= {"origin_file": b.get("origin_file")}
            parsed_buddies.add(Contact.from_dict(b_of_b))
    return parsed_buddies


def _parse_conversations(conversations: list[dict]) -> set[Meeting]:
    cleaned_conversations = set()
    for c in conversations:
        last_message = c.get("value", {}).get("lastMessage", {})

        c |= {
            "cachedDeduplicationKey": last_message.get("cachedDeduplicationKey"),
        }

        if c.get("type", "") == "Meeting" and "meeting" in c.get(
            "threadProperties", {}
        ):
            cleaned_conversations.add(Meeting.from_dict(c))

    return cleaned_conversations


def _parse_reply_chains(reply_chains: list[dict]) -> set[Message]:
    cleaned_reply_chains = set()

    for rc in reply_chains:
        for message_values in rc.get("value", {}).get("messages", {}).values():
            message_values |= {
                "origin_file": rc.get("origin_file"),
            }
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
        sorted(_parse_people(people))
        + sorted(_parse_buddies(buddies))
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
