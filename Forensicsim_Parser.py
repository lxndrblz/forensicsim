# This python autopsy module will parse Leveldb databases of Electron-based Microsoft Teams Desktop Client.
#
# Contact: Alexander Bilz [mail <at> alexbilz [dot] com]
#
# This is free and unencumbered software released into the public domain.
#
# Anyone is free to copy, modify, publish, use, compile, sell, or
# distribute this software, either in source code form or as a compiled
# binary, for any purpose, commercial or non-commercial, and by any
# means.
#
# In jurisdictions that recognize copyright laws, the author or authors
# of this software dedicate any and all copyright interest in the
# software to the public domain. We make this dedication for the benefit
# of the public at large and to the detriment of our heirs and
# successors. We intend this dedication to be an overt act of
# relinquishment in perpetuity of all present and future rights to this
# software under copyright law.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.

# Parses LevelDb's of Electron-based Microsoft Teams Desktop Client
# May 2021
# 
# Comments 
#   Version 1.0 - Initial version - May 2021
# 

import csv
import inspect
import json
import os
import calendar
from datetime import datetime

from subprocess import Popen, PIPE

from java.io import File
from java.lang import ProcessBuilder
from java.util import ArrayList
from java.util.logging import Level
from org.sleuthkit.datamodel import Account
from org.sleuthkit.datamodel.blackboardutils import CommunicationArtifactsHelper
from org.sleuthkit.datamodel.blackboardutils.CommunicationArtifactsHelper import CommunicationDirection
from org.sleuthkit.datamodel.blackboardutils.CommunicationArtifactsHelper import MessageReadStatus
from org.sleuthkit.datamodel.blackboardutils.CommunicationArtifactsHelper import CallMediaType
from org.sleuthkit.datamodel.blackboardutils.attributes import MessageAttachments
from org.sleuthkit.datamodel.blackboardutils.attributes.MessageAttachments import URLAttachment
from org.sleuthkit.autopsy.ingest import IngestModule
from org.sleuthkit.autopsy.ingest.IngestModule import IngestModuleException
from org.sleuthkit.autopsy.ingest import DataSourceIngestModule
from org.sleuthkit.autopsy.ingest import DataSourceIngestModuleProcessTerminator
from org.sleuthkit.autopsy.ingest import IngestModuleFactoryAdapter
from org.sleuthkit.autopsy.ingest import IngestMessage
from org.sleuthkit.autopsy.ingest import IngestServices
from org.sleuthkit.autopsy.coreutils import PlatformUtil
from org.sleuthkit.autopsy.coreutils import Logger
from org.sleuthkit.autopsy.coreutils import ExecUtil
from org.sleuthkit.autopsy.datamodel import ContentUtils
from org.sleuthkit.autopsy.casemodule import Case
from org.sleuthkit.datamodel import CommunicationsManager
from org.sleuthkit.datamodel import BlackboardArtifact
from org.sleuthkit.datamodel import BlackboardAttribute

# Common Prefix Shared for all artefacts
ARTIFACT_PREFIX = "Microsoft Teams "

# Factory that defines the name and details of the module and allows Autopsy
# to create instances of the modules that will do the analysis.
class ForensicIMIngestModuleFactory(IngestModuleFactoryAdapter):

    def __init__(self):
        self.settings = None

    moduleName = "Forensics.im - Microsoft Teams Parser"

    def getModuleDisplayName(self):
        return self.moduleName

    def getModuleDescription(self):
        return "Data Source-level Ingest Module for parsing Microsoft Team's LevelDb databases."

    def getModuleVersionNumber(self):
        return "0.0.1"

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

        communication_manager = Case.getCurrentCase().getSleuthkitCase().getCommunicationsManager()

        self.account = CommunicationsManager.addAccountType(communication_manager, "Microsoft Teams", "Microsoft Teams")

    # Do some basic configuration at the startup of the module
    def startUp(self, context):
        self.context = context
        if PlatformUtil.isWindowsOS():
            self.path_to_executable = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.exe")
            if not os.path.exists(self.path_to_executable):
                raise IngestModuleException("Could not find main.exe within the module directory.")
        else:
            raise IngestModuleException("This Plugin currently only works on Windows based systems.")

        blackboard = Case.getCurrentCase().getServices().getBlackboard()

        # Lets set up some custom attributes for the meetings
        self.att_meeting_id = self.create_attribute_type('MST_MEETING_ID', BlackboardAttribute.TSK_BLACKBOARD_ATTRIBUTE_VALUE_TYPE.STRING, "Meeting ID", blackboard)
        self.att_meeting_subject = self.create_attribute_type('MST_MEETING_SUBJECT', BlackboardAttribute.TSK_BLACKBOARD_ATTRIBUTE_VALUE_TYPE.STRING, "Meeting Subject", blackboard)
        self.att_meeting_start = self.create_attribute_type('MST_MEETING_START', BlackboardAttribute.TSK_BLACKBOARD_ATTRIBUTE_VALUE_TYPE.DATETIME, "Meeting Start", blackboard)
        self.att_meeting_end = self.create_attribute_type('MST_MEETING_END', BlackboardAttribute.TSK_BLACKBOARD_ATTRIBUTE_VALUE_TYPE.DATETIME, "Meeting End", blackboard)
        self.att_meeting_organizer = self.create_attribute_type('MST_MEETING_ORGANIZER', BlackboardAttribute.TSK_BLACKBOARD_ATTRIBUTE_VALUE_TYPE.STRING, "Meeting Organizer", blackboard)
        self.att_meeting_type = self.create_attribute_type('MST_MEETING_TYPE', BlackboardAttribute.TSK_BLACKBOARD_ATTRIBUTE_VALUE_TYPE.STRING, "Meeting Type", blackboard)
        self.att_meeting_compose_time = self.create_attribute_type('MST_MEETING_COMPOSE_TIME', BlackboardAttribute.TSK_BLACKBOARD_ATTRIBUTE_VALUE_TYPE.DATETIME, "Compose Time", blackboard)
        self.att_meeting_original_arrival_time = self.create_attribute_type('MST_MEETING_ORIGINAL_ARRIVAL_TIME', BlackboardAttribute.TSK_BLACKBOARD_ATTRIBUTE_VALUE_TYPE.DATETIME, "Original Arrival Time", blackboard)
        self.att_meeting_client_arrival_time = self.create_attribute_type('MST_MEETING_CLIENT_ARRIVAL_TIME', BlackboardAttribute.TSK_BLACKBOARD_ATTRIBUTE_VALUE_TYPE.DATETIME, "Client Arrival Time", blackboard)


    def _parse_databases(self, content, progress_bar):
        # Create a temporary directory this directory will be used for temporarely storing the artefacts
        try:

            parent_path = content.getParentPath()
            parent_path = parent_path.replace("/", "\\")[1:]

            temp_path_to_data_source = os.path.join(Case.getCurrentCase().getTempDirectory(),
                                                    str(content.getDataSource().getId()))
            temp_path_to_parent = os.path.join(temp_path_to_data_source, parent_path)
            temp_path_to_content = os.path.join(temp_path_to_parent, content.getName())
            os.makedirs(temp_path_to_content)
            self.log(Level.INFO, "Created temporary directory: {}.".format(temp_path_to_content))
        except OSError:
            raise IngestModuleException("Could not create directory: {}.".format(temp_path_to_content))

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
                child_path = os.path.join(path, child_name)
                # ignore relative paths
                if child_name == "." or child_name == "..":
                    continue
                elif child.isFile():
                    ContentUtils.writeToFile(child, File(child_path))
                elif child.isDir():
                    os.mkdir(child_path)
                    self._extract(child, child_path)
            self.log(Level.INFO, "Successfully extracted to {}".format(path))
        except OSError:
            raise IngestModuleException("Could not extract files to directory: {}.".format(path))

    def _analyze(self, content, path, progress_bar):
        # Piece together our command for running parse.exe with the appropriate parameters
        path_to_teams_json = os.path.join(path, "teams.json")
        self.log(Level.INFO, "Executing {} with input path {} and output file {}.".format(self.path_to_executable, path,
                                                                                          path_to_teams_json))
        cmd = ArrayList()
        cmd.add(self.path_to_executable)
        cmd.add("-f")
        cmd.add(path)
        cmd.add("-o")
        cmd.add(path_to_teams_json)
        process_builder = ProcessBuilder(cmd)
        ExecUtil.execute(process_builder, DataSourceIngestModuleProcessTerminator(self.context))

        if not os.path.exists(path_to_teams_json):
            raise IngestModuleException("Unable to find extracted data.")

        # Lets attribute the messages to their respective source files
        imported_records = []
        with open(path_to_teams_json, "rb") as json_file:
            imported_records = json.load(json_file)

        database_sub_files = [i for n, i in enumerate(imported_records) if
                              i.get('origin_file') not in [y.get('origin_file') for y in imported_records[n + 1:]]]

        sleuthkit_case = Case.getCurrentCase().getSleuthkitCase()
        module_name = ForensicIMIngestModuleFactory.moduleName
        # Process all entries per file
        # http://sleuthkit.org/sleuthkit/docs/jni-docs/4.10.2//classorg_1_1sleuthkit_1_1datamodel_1_1blackboardutils_1_1_communication_artifacts_helper.html#aede562cd1efd64588a052cb0013f42cd
        progress_bar.switchToDeterminate(len(imported_records))
        self.progress = 0
        for file in database_sub_files:
            db_file_path = self.get_level_db_file(content, file['origin_file'])
            helper = CommunicationArtifactsHelper(sleuthkit_case, module_name, db_file_path, Account.Type.MESSAGING_APP)
            # Get only the records per file
            file_entries = [d for d in imported_records if d['origin_file'] == file['origin_file']]

            # get the messages
            messages = [d for d in file_entries if d['type'] == 'message']
            self.parse_messages(helper, messages)

            # Update progressbar for every processed file, might not be linear
            self.update_progress(progress_bar, len(messages))

            # get the calls
            calls = [d for d in file_entries if d['type'] == 'call']
            self.parse_calls(helper, calls)

            # Update progressbar for every processed file, might not be linear
            self.update_progress(progress_bar, len(calls))

            # get the meetings
            meetings = [d for d in file_entries if d['type'] == 'meeting']
            self.parse_meetings(db_file_path, meetings)

            # Update progressbar for every processed file, might not be linear
            self.update_progress(progress_bar, len(meetings))


    def update_progress(self, progress_bar, items_processed):
        self.progress += items_processed
        progress_bar.progress(self.progress)

    def get_level_db_file(self, content, filepath):
        # Get the file name
        filename = str(filepath).split('\\')[-1:][0]
        file_manager = Case.getCurrentCase().getServices().getFileManager()
        data_source = content.getDataSource()
        dir_name = os.path.join(content.getParentPath(), content.getName())
        results = file_manager.findFiles(data_source, filename, dir_name)
        if results.isEmpty():
            self.log(Level.INFO, "Unable to locate {}".format(filename))
            return
        db_file = results.get(0)  # Expect a single match so retrieve the first (and only) file
        return db_file

    def date_to_long(self, formatted_date):
        # Timestamp
        dt = datetime.strptime(formatted_date[:19], "%Y-%m-%dT%H:%M:%S")
        time_struct = dt.timetuple()
        timestamp = int(calendar.timegm(time_struct))
        return timestamp

    def parse_meetings(self, db_file_path, meetings):
        blackboard = Case.getCurrentCase().getServices().getBlackboard()
        # Create custom artefacts, because meetings do not exist in Autopsy
        self.art_meeting = self.create_artifact_type("MST_MEETING", "Meeting", blackboard)
        art = db_file_path.newArtifact(self.art_meeting.getTypeID())
        for meeting in meetings:
            # Add the subject as a test attribute to the artefact
            art.addAttribute(BlackboardAttribute(self.att_meeting_subject, ForensicIMIngestModuleFactory.moduleName, meeting["content"]["subject"]))
            art.addAttribute(BlackboardAttribute(self.att_meeting_id, ForensicIMIngestModuleFactory.moduleName, meeting["id"]))
            art.addAttribute(BlackboardAttribute(self.att_meeting_start, ForensicIMIngestModuleFactory.moduleName, self.date_to_long(meeting["content"]["startTime"])))
            art.addAttribute(BlackboardAttribute(self.att_meeting_end, ForensicIMIngestModuleFactory.moduleName, self.date_to_long(meeting["content"]["endTime"])))
            art.addAttribute(BlackboardAttribute(self.att_meeting_organizer, ForensicIMIngestModuleFactory.moduleName, meeting["content"]["organizerId"]))
            art.addAttribute(BlackboardAttribute(self.att_meeting_type, ForensicIMIngestModuleFactory.moduleName, meeting["content"]["meetingType"]))
            art.addAttribute(BlackboardAttribute(self.att_meeting_compose_time, ForensicIMIngestModuleFactory.moduleName, self.date_to_long(meeting["composetime"])))
            art.addAttribute(BlackboardAttribute(self.att_meeting_original_arrival_time, ForensicIMIngestModuleFactory.moduleName, self.date_to_long(meeting["originalarrivaltime"])))
            art.addAttribute(BlackboardAttribute(self.att_meeting_client_arrival_time, ForensicIMIngestModuleFactory.moduleName, self.date_to_long(meeting["clientArrivalTime"])))

        # TODO implement Indexing

    def parse_calls(self, app_db_helper, calls):
        for call in calls:
            from_address = call['call-log']['originator']
            to_address = call['call-log']['target']
            start_date = self.date_to_long(call['call-log']['startTime'])
            end_date = self.date_to_long(call['call-log']['endTime'])
            call_direction = CommunicationDirection.UNKNOWN

            if call['call-log']['callDirection'] == 'incoming':
                call_direction = CommunicationDirection.INCOMING
            elif call['call-log']['callDirection'] == 'outgoing':
                call_direction = CommunicationDirection.OUTGOING

            # TODO implement call state, such as missed/accepted
            artifact = app_db_helper.addCalllog(call_direction, from_address, to_address, start_date, end_date, CallMediaType.UNKNOWN)

    def create_artifact_type(self, artifact_name, artifact_description, blackboard):
        try:
            artifact = blackboard.getOrAddArtifactType(artifact_name, ARTIFACT_PREFIX + artifact_description)
        except Exception as e :
            self.log(Level.INFO, "Error getting or adding artifact type: {} {}".format(artifact_description, str(e)))
        return artifact

    def create_attribute_type(self, attribute_name, type_name, attribute_description, blackboard):
        try:
            attribute = blackboard.getOrAddAttributeType(attribute_name, type_name, attribute_description)
        except Exception as e:
            self.log(Level.INFO, "Error getting or adding attribute type: {} {}".format(attribute_description, str(e)))
        return attribute

    def parse_messages(self, app_db_helper, messages):
        # We will use the integrated add message function to add a TSK_MESSAGE
        # http://sleuthkit.org/autopsy/docs/api-docs/4.12.0//classorg_1_1sleuthkit_1_1autopsy_1_1coreutils_1_1_app_d_b_parser_helper.html#a630bb70bee171df941e363693a1795f3
        for message in messages:
            message_type = "Microsoft Teams (Direct Message)"
            # TODO Change back an email address
            from_address = message["creator"]

            to_address = ""
            subject = None
            message_text = message["content"]
            timestamp = self.date_to_long(message['composetime'])

            # Group by the conversationId, these can be direct messages, but also posts
            thread_id = message["conversationId"]
            # TODO Fix direction, possibly determine direction based on account name?
            direction = CommunicationDirection.UNKNOWN

            # TODO Additional attributes

            # Create the actual artefact in blackboard
            artifact = app_db_helper.addMessage(message_type, direction, from_address, to_address, timestamp,
                                                MessageReadStatus.UNKNOWN, subject, message_text, thread_id)

            file_attachments = ArrayList()
            url_attachments = ArrayList()

            if message['nested_content'] is not None:
                for schema in message['nested_content']:
                    for nc in schema:
                        # Attach files like links, but need to get a different property
                        if nc['@type'] == "http://schema.skype.com/File":
                            url_attachments.add(URLAttachment(nc['objectUrl']))
                        if nc['@type'] == "http://schema.skype.com/HyperLink":
                            url_attachments.add(URLAttachment(nc['url']))
            message_attachments = MessageAttachments(file_attachments, url_attachments)
            app_db_helper.addAttachments(artifact, message_attachments)

    def process(self, data_source, progress_bar):

        # we don't know how long it takes
        progress_bar.switchToIndeterminate()

        # Locate the leveldb database. The full path on Windows systems is something like
        # C:\Users\<user>\AppData\Roaming\Microsoft\Teams\IndexedDB\https_teams.microsoft.com_0.indexeddb.leveldb

        file_manager = Case.getCurrentCase().getServices().getFileManager()
        directory = "https_teams.microsoft.com_0.indexeddb.leveldb"
        # AppData/Roaming/Microsoft/Teams/IndexedDB
        parent_directory = "IndexedDB"
        all_ms_teams_leveldbs = file_manager.findFiles(data_source, directory, parent_directory)

        # Loop over all the files. On a multi user account these could be multiple one.
        directories_to_process = len(all_ms_teams_leveldbs)

        self.log(Level.INFO, "Found {} Microsoft Teams directories to process.".format(directories_to_process))

        for i, content in enumerate(all_ms_teams_leveldbs):
            # Check if the user pressed cancel while we are processing the files
            if self.context.isJobCancelled():
                message = IngestMessage.createMessage(IngestMessage.MessageType.WARNING,
                                                      ForensicIMIngestModuleFactory.moduleName,
                                                      "Analysis of LevelDB has been aborted.")
                IngestServices.getInstance().postMessage(message)
                return IngestModule.ProcessResult.OK
            # Update progress both to the progress bar and log which file is currently processed
            self.log(Level.INFO, "Processing item {} of {}: {}".format(i, directories_to_process, content.getName()))
            # Ignore false positives
            if not content.isDir():
                continue
            # Where the REAL extraction and analysis happens
            self._parse_databases(content, progress_bar)

        # Once we are done, post a message to the ingest messages box
        # Message type DATA seems most appropriate
        # https://www.sleuthkit.org/autopsy/docs/api-docs/4.0/enumorg_1_1sleuthkit_1_1autopsy_1_1ingest_1_1_ingest_message_1_1_message_type.html
        message = IngestMessage.createMessage(IngestMessage.MessageType.DATA, ForensicIMIngestModuleFactory.moduleName,
                                              "Finished analysing the LeveLDB from Microsoft Teams.")
        IngestServices.getInstance().postMessage(message)
        return IngestModule.ProcessResult.OK
