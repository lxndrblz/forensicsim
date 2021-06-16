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

    def _parse_databases(self, content):
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
        self._analyze(content, temp_path_to_content)

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

    def _analyze(self, content, path):
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
        # Process per file
        # TODO Check if it makes sense to change the CommunicationArtifactsHelper to include the self account
        # http://sleuthkit.org/sleuthkit/docs/jni-docs/4.10.2//classorg_1_1sleuthkit_1_1datamodel_1_1blackboardutils_1_1_communication_artifacts_helper.html#aede562cd1efd64588a052cb0013f42cd
        for file in database_sub_files:
            db_file_path = self.get_level_db_file(content, file['origin_file'])
            helper = CommunicationArtifactsHelper(sleuthkit_case, module_name, db_file_path, Account.Type.MESSAGING_APP)
            # Get only the records per file
            file_entries = [d for d in imported_records if d['origin_file'] == file['origin_file']]
            # get the messages
            messages = [d for d in file_entries if d['type'] == 'message']
            self.parse_messages(helper, messages)
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


    def parse_messages(self, app_db_helper, messages):
        # We will use the integrated add message function to add a TSK_MESSAGE
        # http://sleuthkit.org/autopsy/docs/api-docs/4.12.0//classorg_1_1sleuthkit_1_1autopsy_1_1coreutils_1_1_app_d_b_parser_helper.html#a630bb70bee171df941e363693a1795f3
        for message in messages:
            message_type = "Microsoft Teams (Direct Message)"
            # TODO Change back an email address
            from_address = message["imdisplayname"]
            to_address = ""
            subject = None
            message_text = message["content"]
            # Timestamp
            dt = datetime.strptime(message['composetime'][:19], "%Y-%m-%dT%H:%M:%S")
            time_struct = dt.timetuple()
            timestamp = int(calendar.timegm(time_struct))
            # Group by the conversationId, these can be direct messages, but also posts
            thread_id = message["conversationId"]
            # TODO Fix direction, possibly determine direction based on account name?
            direction = CommunicationDirection.UNKNOWN

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
        progress_bar.switchToDeterminate(directories_to_process)

        for i, content in enumerate(all_ms_teams_leveldbs):
            # Check if the user pressed cancel while we are processing the files
            if self.context.isJobCancelled():
                message = IngestMessage.createMessage(IngestMessage.MessageType.WARNING,
                                                      ForensicIMIngestModuleFactory.moduleName,
                                                      "Analysis of LevelDB has been aborted.")
                IngestServices.getInstance().postMessage(message)
                return IngestModule.ProcessResult.OK
            # Update progress both to the progress bar and by loggging
            progress_bar.progress(i)
            self.log(Level.INFO, "Processing item {} of {}: {}".format(i, directories_to_process, content.getName()))
            # Ignore false positives
            if not content.isDir():
                continue
            # Where the REAL extraction and analysis happens
            self._parse_databases(content)

        # Once we are done, post a message to the ingest messages box
        # Message type DATA seems most appropriate
        # https://www.sleuthkit.org/autopsy/docs/api-docs/4.0/enumorg_1_1sleuthkit_1_1autopsy_1_1ingest_1_1_ingest_message_1_1_message_type.html
        message = IngestMessage.createMessage(IngestMessage.MessageType.DATA, ForensicIMIngestModuleFactory.moduleName,
                                              "Finished analysing the LeveLDB from Microsoft Teams.")
        IngestServices.getInstance().postMessage(message)
        return IngestModule.ProcessResult.OK
