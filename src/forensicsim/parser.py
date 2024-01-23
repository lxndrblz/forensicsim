import json
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning
from dataclasses_json import (
    DataClassJsonMixin,
    LetterCase,
    Undefined,
    config,
)

from forensicsim.backend import parse_db, write_results_to_json

# Suppress Beautiful Soup warnings
warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)


def strip_html_tags(value: str) -> str:
    # Get the text of any embedded html, such as divs, a href links
    soup = BeautifulSoup(value, features="html.parser")
    return soup.get_text()


def decode_dict(properties: Union[bytes, str, dict]) -> dict[str, Any]:
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


def decode_timestamp(content_utf8_encoded: str) -> datetime:
    return datetime.utcfromtimestamp(int(content_utf8_encoded) / 1000)


def encode_timestamp(timestamp: Optional[datetime]) -> Optional[str]:
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

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Meeting):
            return NotImplemented
        return self.cached_deduplication_key == other.cached_deduplication_key

    def __hash__(self) -> int:
        return hash(self.cached_deduplication_key)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Meeting):
            return NotImplemented
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
    original_arrival_time: Optional[str] = None
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

    def __post_init__(self) -> None:
        if self.cached_deduplication_key is None:
            self.cached_deduplication_key = str(self.creator) + str(
                self.clientmessageid
            )
        # change record type depending on properties
        if "call-log" in self.properties:
            self.record_type = "call"
        if "activity" in self.properties:
            self.record_type = "reaction"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Message):
            return NotImplemented
        return self.cached_deduplication_key == other.cached_deduplication_key

    def __hash__(self) -> int:
        return hash(self.cached_deduplication_key)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Message):
            return NotImplemented
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

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Contact):
            return NotImplemented
        return self.mri == other.mri

    def __hash__(self) -> int:
        return hash(self.mri)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Contact):
            return NotImplemented
        return self.mri < other.mri


def _parse_people(people: list[dict], version: str) -> set[Contact]:
    parsed_people = set()

    for p in people:
        # Skip empty records / records w/o mri
        if (
            p.get("value") is not None
            and p.get("mri") is not None
            and version in ("v1", "v2")
        ):
            p |= p.get("value", {})
            p |= {"display_name": p.get("displayName")}
            p |= {"user_principal_name": p.get("userPrincipalName")}
            parsed_people.add(Contact.schema().load())
        else:
            print("Teams Version is unknown. Can not extract records of type people.")
    return parsed_people


def _parse_buddies(buddies: list[dict], version: str) -> set[Contact]:
    parsed_buddies = set()

    for b in buddies:
        # Skip empty records
        b_value = b.get("value", {})
        # Fetch relevant data
        if b_value and version in ("v1", "v2"):
            buddies_of_b = b_value.get("buddies", [])
            for b_of_b in buddies_of_b:
                parsed_buddies.add(Contact.from_dict(b_of_b))
        else:
            print("Teams Version is unknown. Can not extract records of type buddies.")
    return parsed_buddies


# Conversations can contain multiple artefacts
# -> If type:Meeting then its a meeting
def _parse_conversations(conversations: list[dict], version: str) -> set[Meeting]:
    cleaned_conversations = set()
    for c in conversations:
        if c.get("value") is not None and version in ("v1", "v2"):
            if c.get("value", {}).get("type", "") == "Meeting" and "meeting" in c.get(
                "value", {}
            ).get("threadProperties", {}):
                c_value = c.get("value", {})
                c |= c_value
                c |= {"thread_properties": c_value.get("threadProperties", {})}
                c |= {"cached_deduplication_key": c.get("id")}
                cleaned_conversations.add(Meeting.from_dict(c))
        else:
            print("Teams Version is unknown. Can not extract records of type meeting.")
    return cleaned_conversations


def _parse_reply_chains(reply_chains: list[dict], version: str) -> set[Message]:
    cleaned_reply_chains = set()
    for rc in reply_chains:
        # Skip empty records
        if rc["value"] is None:
            continue

        # Fetch relevant data
        rc |= rc.get("value", {})
        rc |= {"origin_file": rc.get("origin_file")}

        message_dict = {}
        if version == "v1":
            message_dict = rc.get("value", {}).get("messages", {})
        elif version == "v2":
            message_dict = rc.get("value", {}).get("messageMap", {})
        else:
            print(
                "Teams Version is unknown. Can not extract records of type reply_chains."
            )
            continue

        for k in message_dict:
            md = message_dict[k]
            if (
                md.get("messagetype", "") == "RichText/Html"
                or md.get("messagetype", "") == "Text"
                or md.get("messageType", "") == "RichText/Html"
                or md.get("messageType", "") == "Text"
            ):
                if version == "v1":
                    rc |= {"cached_deduplication_key": md.get("cachedDeduplicationKey")}
                    rc |= {"clientmessageid": md.get("clientmessageid")}
                    rc |= {"composetime": md.get("composetime")}
                    rc |= {"contenttype": md.get("contenttype")}
                    rc |= {"created_time": md.get("createdTime")}
                    rc |= {"is_from_me": md.get("isFromMe")}
                    rc |= {"messagetype": md.get("messagetype")}
                    rc |= {"messageKind": md.get("messageKind")}
                    rc |= {"original_arrival_time": md.get("originalarrivaltime")}

                elif version == "v2":
                    rc |= {"cached_deduplication_key": md.get("dedupeKey")}
                    rc |= {"clientmessageid": md.get("clientMessageId")}
                    # set to clientArrivalTime as compose Time is no longer present
                    rc |= {"composetime": md.get("clientArrivalTime")}
                    rc |= {"contenttype": md.get("contentType")}
                    # set to clientArrivalTime as created time is no longer present
                    rc |= {"created_time": md.get("clientArrivalTime")}
                    rc |= {"is_from_me": md.get("isSentByCurrentUser")}
                    rc |= {"messagetype": md.get("messageType")}
                    rc |= {"original_arrival_time": md.get("originalArrivalTime")}

                # Similar across versions
                rc |= {"creator": md.get("creator")}
                rc |= {"conversation_id": md.get("conversationId")}
                rc |= {"content": md.get("content")}
                rc |= {"client_arrival_time": md.get("clientArrivalTime")}
                rc |= {"version": md.get("version")}
                rc |= {"properties": md.get("properties")}

                cleaned_reply_chains.add(Message.from_dict(rc))

    return cleaned_reply_chains


def identify_teams_version(reply_chains: list[dict]) -> str:
    # Identify version based on reply chain structure
    fingerprint_teams_version = ""
    for rc in reply_chains:
        rc |= rc.get("value", {})
        if rc.get("value", {}).get("messages", {}):
            fingerprint_teams_version = "v1"
        elif rc.get("value", {}).get("messageMap", {}):
            fingerprint_teams_version = "v2"
        else:
            fingerprint_teams_version = "unknown"
        break

    return fingerprint_teams_version


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

    # identify version
    version = identify_teams_version(reply_chains)

    # sort within groups i.e., Contacts, Meetings, Conversations
    parsed_records = (
        sorted(_parse_people(people, version))
        + sorted(_parse_buddies(buddies, version))
        + sorted(_parse_reply_chains(reply_chains, version))
        + sorted(_parse_conversations(conversations, version))
    )
    return [r.to_dict() for r in parsed_records]


def process_db(
    input_path: Path,
    output_path: Path,
    blob_path: Optional[Path] = None,
    do_not_filter: Optional[bool] = True,
) -> None:
    if not input_path.parts[-1].endswith(".leveldb"):
        raise ValueError(f"Expected a leveldb folder. Path: {input_path}")

    if blob_path is not None and not blob_path.parts[-1].endswith(".blob"):
        raise ValueError(f"Expected a .blob folder. Path: {blob_path}")

    extracted_values = parse_db(input_path, blob_path, do_not_filter)
    parsed_records = parse_records(extracted_values)
    write_results_to_json(parsed_records, output_path)
