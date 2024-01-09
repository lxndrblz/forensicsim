# This python autopsy module will parse Leveldb databases of Electron-based Microsoft Teams Desktop Client.
#
# Contact: Alexander Bilz [mail <at> alexbilz [dot] com]
#

# MIT License
#
# Copyright (c) 2021 Alexander Bilz
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# Parses LevelDb's of Electron-based Microsoft Teams Desktop Client
# May 2021
#
# Comments
#   Version 1.0 - Initial version - May 2021
#

import calendar
import inspect
import json
import os
from datetime import datetime

from java.io import File
from java.lang import ProcessBuilder
from java.util import ArrayList
from java.util.logging import Level
from org.sleuthkit.autopsy.casemodule import Case, NoCurrentCaseException
from org.sleuthkit.autopsy.coreutils import ExecUtil, Logger, PlatformUtil
from org.sleuthkit.autopsy.datamodel import ContentUtils
from org.sleuthkit.autopsy.ingest import (
    DataSourceIngestModule,
    DataSourceIngestModuleProcessTerminator,
    IngestMessage,
    IngestModule,
    IngestModuleFactoryAdapter,
    IngestServices,
)
from org.sleuthkit.autopsy.ingest.IngestModule import IngestModuleException
from org.sleuthkit.datamodel import (
    BlackboardArtifact,
    BlackboardAttribute,
    CommunicationsManager,
    TskCoreException,
    TskData,
)
from org.sleuthkit.datamodel.Blackboard import BlackboardException
from org.sleuthkit.datamodel.blackboardutils import CommunicationArtifactsHelper
from org.sleuthkit.datamodel.blackboardutils.attributes import MessageAttachments
from org.sleuthkit.datamodel.blackboardutils.attributes.MessageAttachments import (
    URLAttachment,
)
from org.sleuthkit.datamodel.blackboardutils.CommunicationArtifactsHelper import (
    CallMediaType,
    CommunicationDirection,
    MessageReadStatus,
)

# Common Prefix Shared for all artefacts
ARTIFACT_PREFIX = "Microsoft Teams"
# The directory names that are used by MS Teams
# https_teams.microsoft.com_0.indexeddb.leveldb is for business and educational accounts
# https_teams.live.com_0.indexeddb.leveldb is for private organisations

DIRECTORIES = [
    "https_teams.microsoft.com_0.indexeddb.leveldb",
    "https_teams.live.com_0.indexeddb.leveldb",
]


# Factory that defines the name and details of the module and allows Autopsy
# to create instances of the modules that will do the analysis.
class ForensicIMIngestModuleFactory(IngestModuleFactoryAdapter):
    def __init__(self):
        self.settings = None

    moduleName = "Microsoft Teams Parser"

    def getModuleDisplayName(self):
        return self.moduleName

    def getModuleDescription(self):
        return "Data Source-level Ingest Module for parsing Microsoft Team's LevelDb databases."

    def getModuleVersionNumber(self):
        return "1.4.00"

    def isDataSourceIngestModuleFactory(self):
        return True

    def createDataSourceIngestModule(self, ingestOptions):
        return ForensicIMIngestModule(self.settings)


# Data Source-level ingest module.  One gets created per data source.
class ForensicIMIngestModule(DataSourceIngestModule):
    _logger = Logger.getLogger(ForensicIMIngestModuleFactory.moduleName)

    def log(self, level, msg):
        self._logger.logp(level, self.__class__.__name__, inspect.stack()[1][3], msg)
        self._logger = Logger.getLogger(self.__class__.__name__)

    def __init__(self, settings):
        self.context = None
        self.local_settings = settings
        self._logger = Logger.getLogger(self.__class__.__name__)
        self._logger.log(Level.SEVERE, "Starting Forensics.im Plugin")
        self.path_to_executable = None

        communication_manager = (
            Case.getCurrentCase().getSleuthkitCase().getCommunicationsManager()
        )

        self.account = CommunicationsManager.addAccountType(
            communication_manager, "Microsoft Teams", "Microsoft Teams"
        )

    # Do some basic configuration at the startup of the module
    def startUp(self, context):
        self.context = context
        if PlatformUtil.isWindowsOS():
            self.path_to_executable = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "ms_teams_parser.exe"
            )
            if not os.path.exists(self.path_to_executable):
                raise IngestModuleException(
                    "Could not find main.exe within the module directory."
                )
        else:
            raise IngestModuleException(
                "This Plugin currently only works on Windows based systems."
            )

        blackboard = Case.getCurrentCase().getServices().getBlackboard()

        # reaction attributes

        self.att_reaction_message_id = self.create_attribute_type(
            "MST_MESSAGE_ID",
            BlackboardAttribute.TSK_BLACKBOARD_ATTRIBUTE_VALUE_TYPE.STRING,
            "Message ID",
            blackboard,
        )
        self.att_reaction_thread_id = self.create_attribute_type(
            "MST_THREAD_ID",
            BlackboardAttribute.TSK_BLACKBOARD_ATTRIBUTE_VALUE_TYPE.STRING,
            "Thread ID",
            blackboard,
        )
        self.att_reaction_source_user_id = self.create_attribute_type(
            "MST_SOURCE_USER_ID",
            BlackboardAttribute.TSK_BLACKBOARD_ATTRIBUTE_VALUE_TYPE.STRING,
            "Source User",
            blackboard,
        )
        self.att_reaction_target_user_id = self.create_attribute_type(
            "MST_TARGET_USER_ID",
            BlackboardAttribute.TSK_BLACKBOARD_ATTRIBUTE_VALUE_TYPE.STRING,
            "Target User",
            blackboard,
        )
        self.att_reaction_message_preview = self.create_attribute_type(
            "MST_MESSAGE_PREVIEW",
            BlackboardAttribute.TSK_BLACKBOARD_ATTRIBUTE_VALUE_TYPE.STRING,
            "Preview",
            blackboard,
        )
        self.att_reaction_activity = self.create_attribute_type(
            "MST_ACTIVITY_SUBTYPE",
            BlackboardAttribute.TSK_BLACKBOARD_ATTRIBUTE_VALUE_TYPE.STRING,
            "Activity",
            blackboard,
        )
        self.att_reaction_timestamp = self.create_attribute_type(
            "MST_TIMESTAMP",
            BlackboardAttribute.TSK_BLACKBOARD_ATTRIBUTE_VALUE_TYPE.DATETIME,
            "Timestamp",
            blackboard,
        )

    def _parse_databases(self, content, progress_bar):
        # Create a temporary directory this directory will be used for temporarily storing the artefacts
        try:
            parent_path = content.getParentPath()
            parent_path = parent_path.replace("/", "\\")[1:]

            temp_path_to_data_source = os.path.join(
                Case.getCurrentCase().getTempDirectory(),
                str(content.getDataSource().getId()),
            )
            temp_path_to_parent = os.path.join(temp_path_to_data_source, parent_path)
            temp_path_to_content = os.path.join(temp_path_to_parent, content.getName())
            os.makedirs(temp_path_to_content)
            self.log(
                Level.INFO,
                f"Created temporary directory: {temp_path_to_content}.",
            )
        except OSError:
            raise IngestModuleException(
                f"Could not create directory: {temp_path_to_content}."
            )

        # At first extract the desired artefacts to our newly created temp directory
        self._extract(content, temp_path_to_content)

        # Finally we can parse the extracted artefacts
        self._analyze(content, temp_path_to_content, progress_bar)

    def _extract(self, content, path):
        # This functions extracts the artefacts from the datasource
        try:
            children = content.getChildren()
            for child in children:
                child_name = child.getName()
                # Skip any unallocated files
                if child.isMetaFlagSet(
                    TskData.TSK_FS_META_FLAG_ENUM.UNALLOC
                ) or child.isDirNameFlagSet(TskData.TSK_FS_NAME_FLAG_ENUM.UNALLOC):
                    continue
                child_path = os.path.join(path, child_name)
                # ignore relative paths
                if child_name == "." or child_name == "..":
                    continue
                elif child.isFile():  # noqa: RET507
                    ContentUtils.writeToFile(child, File(child_path))
                elif child.isDir():
                    os.mkdir(child_path)
                    self._extract(child, child_path)
            self.log(Level.INFO, f"Successfully extracted to {path}")
        except OSError:
            raise IngestModuleException(
                f"Could not extract files to directory: {path}."
            )

    def _analyze(self, content, path, progress_bar):
        # Piece together our command for running parse.exe with the appropriate parameters
        path_to_teams_json = os.path.join(path, "teams.json")
        self.log(
            Level.INFO,
            "Executing {} with input path {} and output file {}.".format(
                self.path_to_executable, path, path_to_teams_json
            ),
        )
        cmd = ArrayList()
        cmd.add(self.path_to_executable)
        cmd.add("--filepath")
        cmd.add(path)
        cmd.add("--outputpath")
        cmd.add(path_to_teams_json)
        process_builder = ProcessBuilder(cmd)
        ExecUtil.execute(
            process_builder, DataSourceIngestModuleProcessTerminator(self.context)
        )

        if not os.path.exists(path_to_teams_json):
            raise IngestModuleException("Unable to find extracted data.")

        imported_records = []
        with open(path_to_teams_json, "rb") as json_file:
            imported_records = json.load(json_file)

        if imported_records is not None:
            self._process_imported_records(imported_records, content, progress_bar)
        else:
            raise IngestModuleException("Extracted data is None.")

    def _process_imported_records(self, imported_records, content, progress_bar):
        # Lets attribute the messages to their respective source files
        database_sub_files = [
            i
            for n, i in enumerate(imported_records)
            if i.get("origin_file")
            not in [y.get("origin_file") for y in imported_records[n + 1 :]]
        ]
        try:
            for file in database_sub_files:
                user_account_instance = None
                teams_leveldb_file_path = self.get_level_db_file(
                    content, file["origin_file"]
                )
                # Get only the records per file
                records = [
                    d
                    for d in imported_records
                    if d["origin_file"] == file["origin_file"]
                ]
                try:
                    user_account_instance = self.get_user_account(records)
                except:
                    self._logger.log(
                        Level.WARNING,
                        "Error querying for the user account from the LevelDB",
                    )

                current_case = Case.getCurrentCaseThrows()
                if user_account_instance is None:
                    helper = CommunicationArtifactsHelper(
                        current_case.getSleuthkitCase(),
                        ARTIFACT_PREFIX,
                        teams_leveldb_file_path,
                        self.account,
                    )
                else:
                    helper = CommunicationArtifactsHelper(
                        current_case.getSleuthkitCase(),
                        ARTIFACT_PREFIX,
                        teams_leveldb_file_path,
                        self.account,
                        self.account,
                        user_account_instance,
                    )
                # parse the remaining artefacts
                # contacts
                contacts = [d for d in records if d["record_type"] == "contact"]
                self.parse_contacts(contacts, helper)

                # calllogs
                calllogs = [d for d in records if d["record_type"] == "call"]
                self.parse_calllogs(calllogs, helper)

                # messages
                messages = [d for d in records if d["record_type"] == "message"]
                self.parse_messages(messages, helper, teams_leveldb_file_path)

                # meetings does not have a convenient helper so we pass the file
                meetings = [d for d in records if d["record_type"] == "meeting"]
                self.parse_meetings(meetings, teams_leveldb_file_path)

        except NoCurrentCaseException as ex:
            self._logger.log(Level.WARNING, "No case currently open.", ex)

    def parse_reaction(
        self,
        message_id,
        thread_id,
        source_user,
        target_user,
        message_preview,
        activity,
        timestamp,
        database_file,
    ):
        blackboard = Case.getCurrentCase().getServices().getBlackboard()
        try:
            self.art_meeting = self.create_artifact_type(
                "MST_REACTION", "Reactions", blackboard
            )

            art = database_file.newArtifact(self.art_meeting.getTypeID())
            # Add the subject as a test attribute to the artefact
            art.addAttribute(
                BlackboardAttribute(
                    self.att_reaction_message_id,
                    ForensicIMIngestModuleFactory.moduleName,
                    message_id,
                )
            )

            art.addAttribute(
                BlackboardAttribute(
                    self.att_reaction_thread_id,
                    ForensicIMIngestModuleFactory.moduleName,
                    thread_id,
                )
            )
            art.addAttribute(
                BlackboardAttribute(
                    self.att_reaction_source_user_id,
                    ForensicIMIngestModuleFactory.moduleName,
                    source_user,
                )
            )
            art.addAttribute(
                BlackboardAttribute(
                    self.att_reaction_target_user_id,
                    ForensicIMIngestModuleFactory.moduleName,
                    target_user,
                )
            )
            art.addAttribute(
                BlackboardAttribute(
                    self.att_reaction_message_preview,
                    ForensicIMIngestModuleFactory.moduleName,
                    message_preview,
                )
            )
            art.addAttribute(
                BlackboardAttribute(
                    self.att_reaction_activity,
                    ForensicIMIngestModuleFactory.moduleName,
                    activity,
                )
            )
            art.addAttribute(
                BlackboardAttribute(
                    self.att_reaction_timestamp,
                    ForensicIMIngestModuleFactory.moduleName,
                    timestamp,
                )
            )
            self.index_artifact(art)
        except TskCoreException as ex:
            # Severe error trying to add to case database.. case is not complete.
            # These exceptions are thrown by the CommunicationArtifactsHelper.
            self._logger.log(
                Level.SEVERE,
                "Failed to add message artifacts to the case database.",
                ex,
            )
        except BlackboardException as ex:
            # Failed to post notification to blackboard
            self._logger.log(
                Level.WARNING, "Failed to post message artifact to the blackboard", ex
            )

    def parse_contacts(self, contacts, helper):
        # Todo possibly write a owner parser overriding the TskContactsParser, problem is that it expects a resultset
        try:
            for contact in contacts:
                contact_name = contact["displayName"]
                contact_phone_number = None
                contact_home_phone_number = None
                contact_mobile_phone_number = None
                contact_email = contact["email"]
                # ADD the TSK ID as an additional attribute
                additional_attributes = ArrayList()
                additional_attributes.add(
                    BlackboardAttribute(
                        BlackboardAttribute.ATTRIBUTE_TYPE.TSK_ID,
                        ARTIFACT_PREFIX,
                        contact["mri"],
                    )
                )
                helper.addContact(
                    contact_name,
                    contact_phone_number,
                    contact_home_phone_number,
                    contact_mobile_phone_number,
                    contact_email,
                    additional_attributes,
                )
        except TskCoreException as e:
            self._logger.log(
                Level.SEVERE,
                "Error adding Microsoft Teams contact artifacts to the case database.",
                e,
            )
        except BlackboardException as e:
            self._logger.log(
                Level.WARNING, "Error posting contact artifact to the blackboard.", e
            )

    def parse_calllogs(self, calls, helper):
        # Query for call logs and iterate row by row adding
        # each call log artifact
        try:
            for call in calls:
                call_direction = self.deduce_call_direction(
                    call["properties"]["call-log"]["callDirection"]
                )
                from_address = call["properties"]["call-log"]["originator"]
                to_address = call["properties"]["call-log"]["target"]
                start_date = self.date_to_long(
                    call["properties"]["call-log"]["startTime"]
                )
                end_date = self.date_to_long(call["properties"]["call-log"]["endTime"])

                helper.addCalllog(
                    call_direction,
                    from_address,
                    to_address,
                    start_date,
                    end_date,
                    CallMediaType.UNKNOWN,
                )
        except TskCoreException as ex:
            # These exceptions are thrown by the CommunicationArtifactsHelper.
            self._logger.log(
                Level.SEVERE,
                "Failed to add call log artifacts to the case database.",
                ex,
            )
        except BlackboardException as ex:
            # Failed to post notification to blackboard
            self._logger.log(
                Level.WARNING, "Failed to post call log artifact to the blackboard", ex
            )

    def parse_messages(self, messages, helper, teams_leveldb_file_path):
        # Query for messages and iterate row by row adding
        # each message artifact
        try:
            for message in messages:
                message_type = ARTIFACT_PREFIX
                message_id = message["clientmessageid"]
                direction = self.deduce_message_direction(message["isFromMe"])
                phone_number_from = message["creator"]
                # TODO Fix To Number
                phone_number_to = ""
                message_date_time = self.date_to_long(message["composetime"])
                message_read_status = MessageReadStatus.UNKNOWN
                subject = None
                message_text = message["content"]
                # Group by the conversationId, these can be direct messages, but also posts
                thread_id = message["conversationId"]

                additional_attributes = ArrayList()
                additional_attributes.add(
                    BlackboardAttribute(
                        BlackboardAttribute.ATTRIBUTE_TYPE.TSK_ID,
                        ARTIFACT_PREFIX,
                        message_id,
                    )
                )
                # additional_attributes.add(
                #     BlackboardAttribute(BlackboardAttribute.ATTRIBUTE_TYPE.TSK_DATETIME_DELETED, ARTIFACT_PREFIX,
                #                         message_date_time_deleted))

                artifact = helper.addMessage(
                    message_type,
                    direction,
                    phone_number_from,
                    phone_number_to,
                    message_date_time,
                    message_read_status,
                    subject,
                    message_text,
                    thread_id,
                    additional_attributes,
                )

                file_attachments = ArrayList()
                url_attachments = ArrayList()

                if "properties" in message:
                    # process links
                    if "links" in message["properties"]:
                        for link in message["properties"]["links"]:
                            url_attachments.add(URLAttachment(link["url"]))
                    # process emotions
                    if "emotions" in message["properties"]:
                        for emotion in message["properties"]["emotions"]:
                            # emotions are grouped by their key like, heart..
                            # Add one reaction entry by per
                            for user in emotion["users"]:
                                self.parse_reaction(
                                    message_id,
                                    thread_id,
                                    user["mri"],
                                    phone_number_from,
                                    message_text,
                                    emotion["key"],
                                    int(user["time"] / 1000),
                                    teams_leveldb_file_path,
                                )
                    # process the attachments
                    if "files" in message["properties"]:
                        for attachment in message["properties"]["files"]:
                            # Attach files like links
                            url_attachments.add(URLAttachment(attachment["objectUrl"]))
                message_attachments = MessageAttachments(
                    file_attachments, url_attachments
                )
                helper.addAttachments(artifact, message_attachments)

        except TskCoreException as ex:
            # Severe error trying to add to case database.. case is not complete.
            # These exceptions are thrown by the CommunicationArtifactsHelper.
            self._logger.log(
                Level.SEVERE,
                "Failed to add message artifacts to the case database.",
                ex,
            )
        except BlackboardException as ex:
            # Failed to post notification to blackboard
            self._logger.log(
                Level.WARNING, "Failed to post message artifact to the blackboard", ex
            )

    def parse_meetings(self, meetings, database_file):
        try:
            for meeting in meetings:
                # TSK_CALENDAR_ENTRY http://sleuthkit.org/sleuthkit/docs/jni-docs/4.6/artifact_catalog_page.html
                art = database_file.newArtifact(
                    BlackboardArtifact.ARTIFACT_TYPE.TSK_CALENDAR_ENTRY
                )
                # Required Attributes
                calendar_entry_type = "Meeting"
                calendar_entry_start_time = self.date_to_long(
                    meeting["threadProperties"]["meeting"]["startTime"]
                )
                calendar_entry_description = meeting["threadProperties"]["meeting"][
                    "subject"
                ]
                # Optional Attributes
                calendar_entry_end_time = self.date_to_long(
                    meeting["threadProperties"]["meeting"]["endTime"]
                )
                calendar_entry_organizer = meeting["threadProperties"]["meeting"][
                    "organizerId"
                ]

                art.addAttribute(
                    BlackboardAttribute(
                        BlackboardAttribute.ATTRIBUTE_TYPE.TSK_CALENDAR_ENTRY_TYPE,
                        ARTIFACT_PREFIX,
                        calendar_entry_type,
                    )
                )
                art.addAttribute(
                    BlackboardAttribute(
                        BlackboardAttribute.ATTRIBUTE_TYPE.TSK_DATETIME_START,
                        ARTIFACT_PREFIX,
                        calendar_entry_start_time,
                    )
                )
                art.addAttribute(
                    BlackboardAttribute(
                        BlackboardAttribute.ATTRIBUTE_TYPE.TSK_DESCRIPTION,
                        ARTIFACT_PREFIX,
                        calendar_entry_description,
                    )
                )
                art.addAttribute(
                    BlackboardAttribute(
                        BlackboardAttribute.ATTRIBUTE_TYPE.TSK_DATETIME_END,
                        ARTIFACT_PREFIX,
                        calendar_entry_end_time,
                    )
                )
                art.addAttribute(
                    BlackboardAttribute(
                        BlackboardAttribute.ATTRIBUTE_TYPE.TSK_ID,
                        ARTIFACT_PREFIX,
                        calendar_entry_organizer,
                    )
                )
                self.index_artifact(art)

        except TskCoreException as ex:
            # Severe error trying to add to case database.. case is not complete.
            # These exceptions are thrown by the CommunicationArtifactsHelper.
            self._logger.log(
                Level.SEVERE,
                "Failed to add message artifacts to the case database.",
                ex,
            )
        except BlackboardException as ex:
            # Failed to post notification to blackboard
            self._logger.log(
                Level.WARNING, "Failed to post message artifact to the blackboard", ex
            )

    def index_artifact(self, artifact):
        # Index the artifact for keyword search
        try:
            blackboard = Case.getCurrentCase().getServices().getBlackboard()
            blackboard.indexArtifact(artifact)
        except BlackboardException as ex:
            self._logger.log(Level.SEVERE, "Failed to index artifact.", ex)

    def get_user_account(self, records):
        # TODO Fix lookup mechanism
        return None

    def update_progress(self, progress_bar, items_processed):
        self.progress += items_processed
        progress_bar.progress(self.progress)

    def get_level_db_file(self, content, filepath):
        # Get the file name
        filename = str(filepath).split("\\")[-1:][0]
        file_manager = Case.getCurrentCase().getServices().getFileManager()
        data_source = content.getDataSource()
        dir_name = os.path.join(content.getParentPath(), content.getName())
        results = file_manager.findFiles(data_source, filename, dir_name)
        if results.isEmpty():
            self.log(Level.INFO, f"Unable to locate {filename}")
            return None
        return results.get(
            0
        )  # Expect a single match so retrieve the first (and only) file

    def date_to_long(self, formatted_date):
        # Timestamp
        dt = datetime.strptime(formatted_date[:19], "%Y-%m-%dT%H:%M:%S")
        time_struct = dt.timetuple()
        return int(calendar.timegm(time_struct))

    # Extract the direction of a phone call
    def deduce_call_direction(self, direction):
        call_direction = CommunicationDirection.UNKNOWN
        if direction is not None:
            if direction == "incoming":
                call_direction = CommunicationDirection.INCOMING
            elif direction == "outgoing":
                call_direction = CommunicationDirection.OUTGOING
        return call_direction

    def deduce_message_direction(self, is_from_me):
        call_direction = CommunicationDirection.INCOMING
        if is_from_me is True:
            call_direction = CommunicationDirection.OUTGOING
        return call_direction

    def create_artifact_type(self, artifact_name, artifact_description, blackboard):
        try:
            artifact = blackboard.getOrAddArtifactType(
                artifact_name, ARTIFACT_PREFIX + " " + artifact_description
            )
        except Exception as e:
            self.log(
                Level.INFO,
                "Error getting or adding artifact type: {} {}".format(
                    artifact_description, str(e)
                ),
            )
        return artifact

    def create_attribute_type(
        self, attribute_name, type_name, attribute_description, blackboard
    ):
        try:
            attribute = blackboard.getOrAddAttributeType(
                attribute_name, type_name, attribute_description
            )
        except Exception as e:
            self.log(
                Level.INFO,
                "Error getting or adding attribute type: {} {}".format(
                    attribute_description, str(e)
                ),
            )
        return attribute

    def process(self, data_source, progress_bar):
        # we don't know how long it takes
        progress_bar.switchToIndeterminate()

        # Locate the leveldb database. The full path on Windows systems is something like
        # C:\Users\<user>\AppData\Roaming\Microsoft\Teams\IndexedDB\https_teams.microsoft.com_0.indexeddb.leveldb

        file_manager = Case.getCurrentCase().getServices().getFileManager()

        # There could be both personal and organisational clients on the matchine
        for directory in DIRECTORIES:
            all_ms_teams_leveldbs = file_manager.findFiles(data_source, directory)

            # Loop over all the files. On a multi user account these could be multiple one.
            directories_to_process = len(all_ms_teams_leveldbs)

            self.log(
                Level.INFO,
                f"Found {directories_to_process} {directory} directories to process.",
            )

            for i, content in enumerate(all_ms_teams_leveldbs):
                # Check if the user pressed cancel while we are processing the files
                if self.context.isJobCancelled():
                    message = IngestMessage.createMessage(
                        IngestMessage.MessageType.WARNING,
                        ForensicIMIngestModuleFactory.moduleName,
                        "Analysis of LevelDB has been aborted.",
                    )
                    IngestServices.getInstance().postMessage(message)
                    return IngestModule.ProcessResult.OK
                # Update progress both to the progress bar and log which file is currently processed
                self.log(
                    Level.INFO,
                    "Processing item {} of {}: {}".format(
                        i, directories_to_process, content.getName()
                    ),
                )
                # Ignore false positives
                if not content.isDir():
                    continue
                # Where the REAL extraction and analysis happens
                self._parse_databases(content, progress_bar)

        # Once we are done, post a message to the ingest messages box
        # Message type DATA seems most appropriate
        # https://www.sleuthkit.org/autopsy/docs/api-docs/4.0/enumorg_1_1sleuthkit_1_1autopsy_1_1ingest_1_1_ingest_message_1_1_message_type.html
        message = IngestMessage.createMessage(
            IngestMessage.MessageType.DATA,
            ForensicIMIngestModuleFactory.moduleName,
            "Finished analysing the LeveLDB from Microsoft Teams.",
        )
        IngestServices.getInstance().postMessage(message)
        return IngestModule.ProcessResult.OK
