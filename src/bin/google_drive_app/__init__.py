"""
This module includes classes necessary to export and import lookups to Google spreadsheets.


from google_drive_app import GoogleLookupSync

login = 'someone@gmail.com'
password = 'super_secret'

google_lookup_sync = GoogleLookupSync(login, password)

google_lookup_sync.import_to_lookup_file(lookup_name='some_lookup.csv', namespace='search', owner='nobody', google_spread_sheet_name='test_case_import', worksheet_name='data', session_key=session_key)

"""

import os
import csv
import shutil
import logging
import lookupfiles
import gspread
from splunk.appserver.mrsparkle.lib.util import make_splunkhome_path

class GoogleLookupSync(object):
    """
    This class performs operation for importing content from Google Drive to Splunk.
    """
    
    class OperationAction:
        OVERWRITE = 1
        APPEND    = 2
        
    class Operation:
        IMPORT      = 1
        EXPORT      = 2
        SYNCHRONIZE = 3
        
    def __init__(self, login=None, password=None, oauth2credentials=None, logger=None):
        
        self.gspread_client = None
                
        if oauth2credentials is not None:
            self.authenticate_by_oauth2()
        else:
            self.authenticate_by_password(login, password)
            
        self.logger = logger
        
        # Initialize a logger. This will cause it be initialized if one is not set yet.
        self.get_logger()
        
        #SPL-95681
        self.update_lookup_with_rest = False
        
    def authenticate_by_password(self, login, password):
        """
        Authenticate to Google and initialize a gspread client.
        
        Args:
          login (str): The login to use for authenticating to Google
          password (str): The password to use for authenticating to Google
        """
        
        # Make sure a login name and password were provided
        if login is None or password is None:
            raise ValueError("Neither a login name nor a password was provided")
        
        self.gspread_client = gspread.login(login, password)
        return self.gspread_client
        
    def authenticate_by_oauth2(self, oauth2credentials):
        """
        Authenticate to Google and initialize a gspread client using OAuth2
        
        Args:
          oauth2credentials (OAuth2Credentials): The oauth2credentials to use for authenticating.
        """
        
        self.gspread_client = gspread.authorize(oauth2credentials)
        return self.gspread_client
    
    def open_google_spreadsheet(self, title=None, key=None):
        """
        Open the spreadsheet with the given title or key, Either the key or title must be provided.
        
        If both are provided, then the title will be used. If a sheet could not be opened with the title, then the key will be used.
        
        Args:
          title (str, optional): The title of the document
          key (str, optional): The key of the document
          
        Returns:
          The Google spreadsheet object
        """
        
        if title is None and key is None:
            raise ValueError("You must supply either the title or the key of the sheet you want to open")
        
        google_spread_sheet = None
        
        # Try to open the file by the title
        if title is not None:
            google_spread_sheet = self.gspread_client.open(title)
            
            
        # If we don't have the sheet yet, try using the key
        if google_spread_sheet is None and key is not None:
            self.gspread_client.open_by_key(key)
        
        return google_spread_sheet
    
    def get_lookup_file_row_count(self, lookup_file_path):
        pass
    
    def copy_file(self, src, dst):
        pass
    
    def set_logger(self, logger):
        self.logger = logger
    
    def get_logger(self):
        """
        Setup a logger for this class.
        
        Returns:
          A logger
        """
    
        try:
            return logger
        except:
            pass
        
        if self.logger is not None:
            return self.logger
    
        logger = logging.getLogger('splunk.google_drive.GoogleLookupSync')
        logger.setLevel(logging.DEBUG)
        #logger.propagate = False # Prevent the log messages from being duplicated in the python.log file
    
        #file_handler = logging.handlers.RotatingFileHandler(make_splunkhome_path(['var', 'log', 'splunk', 'google_lookup_sync.log']), maxBytes=25000000, backupCount=5)
    
        #formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        #file_handler.setFormatter(formatter)
        #logger.addHandler(file_handler)
        
        self.logger = logger
        return logger
    
    def import_to_lookup_file_by_transform(self, lookup_transform, namespace, owner, google_spread_sheet_name, worksheet_name, session_key, create_if_non_existent=False):
        """
        Import the spreadsheet from Google to the given lookup file.
        
        Args:
          lookup_transform (str): The name of the lookup file transform to write 
          namespace (str): 
          owner (str): 
          google_spread_sheet_name (str): 
          worksheet_name (str): 
          session_key (str): 
          create_if_non_existent (bool, optional): Defaults to False.
        """
        transform = lookupfiles.get_lookup_table_location(lookup_transform, namespace, owner, session_key, True)
        
        self.import_to_lookup_file(transform.filename, namespace, owner, google_spread_sheet_name, worksheet_name, session_key, create_if_non_existent)
    
    def import_to_lookup_file(self, lookup_name, namespace, owner, google_spread_sheet_name, worksheet_name, session_key, create_if_non_existent=False):
        """
        Import the spreadsheet from Google to the given lookup file.
        
        Args:
          lookup_name (str): The name of the lookup file to write (not the full path, just the stanza name)
          namespace (str): 
          owner (str): 
          google_spread_sheet_name (str): 
          worksheet_name (str): 
          session_key (str): 
          create_if_non_existent (bool, optional): Defaults to False.
        """
        
        splunk_lookup_table = lookupfiles.SplunkLookupTableFile.get(lookupfiles.SplunkLookupTableFile.build_id(lookup_name, namespace, owner), sessionKey=session_key)

        destination_full_path = splunk_lookup_table.path
        
        if namespace is None and splunk_lookup_table is not None:
            namespace = splunk_lookup_table.namespace
            
        if owner is None:
            owner = "nobody"
        
        self.get_logger().info("Lookup file path=%s", destination_full_path)
        
        if destination_full_path is None and not create_if_non_existent:
            raise Exception("Lookup file to import into does not exist")
        
        elif create_if_non_existent and destination_full_path is None:
            # TODO handle user-based lookups
            destination_full_path = make_splunkhome_path(['etc', 'apps', namespace, 'lookups', lookup_name])
        
        self.import_to_lookup_file_full_path(destination_full_path, namespace, owner, google_spread_sheet_name, worksheet_name, session_key, create_if_non_existent, lookup_name=lookup_name)
        
    def import_to_lookup_file_full_path(self, destination_full_path, namespace, owner, google_spread_sheet_name, worksheet_name, session_key, create_if_non_existent=False, lookup_name=None):
        """
        Import the spreadsheet from Google to the given lookup file.
        
        Args:
          destination_full_path (str): The full path of the file to write out
          namespace (str): 
          owner (str): 
          google_spread_sheet_name (str): 
          worksheet_name (str): 
          session_key (str):
          lookup_name (str): The name of the lookup file to write (not the full path, just the stanza name). This is necessary to use Splunk's safe method of copying.
          create_if_non_existent (bool, optional): Defaults to False.
        """
        
        # Open the spreadsheet
        google_spread_sheet = self.open_google_spreadsheet(google_spread_sheet_name)
        
        # Open or make the worksheet
        google_work_sheet = self.get_or_make_sheet_if_necessary(google_spread_sheet, worksheet_name)
        
        # Make a temporary lookup file
        temp_file_handle = lookupfiles.get_temporary_lookup_file()
        temp_file_name = temp_file_handle.name
        
        # Get the contents of spreadsheet and import it into the lookup
        list_of_lists = google_work_sheet.get_all_values()
        
        #with temp_file: #open(temp_file.name, 'w') as temp_file_handle:
        try:
            if temp_file_handle is not None and os.path.isfile(temp_file_name):
                
                # Open a CSV writer to edit the file
                csv_writer = csv.writer(temp_file_handle, lineterminator='\n')
                
                for row in list_of_lists:
                    
                    # Update the CSV with the row
                    csv_writer.writerow(row)
        
        finally:   
            if temp_file_handle is not None:
                temp_file_handle.close()
        
        # Determine if the lookup file exists, create it if it doesn't
        lookup_file_exists = os.path.exists(destination_full_path)
        
        if self.update_lookup_with_rest == False or not lookup_file_exists or lookup_name is None:
            
            # If we are not allowed to make the lookup file, then throw an exception
            if not lookup_file_exists and not create_if_non_existent:
                raise Exception("The lookup file to import the content to does not exist")
            
            # Manually copy the file to create it
            if lookup_file_exists:
                shutil.copy(temp_file_name, destination_full_path)
            else:
                shutil.move(temp_file_name, destination_full_path)
                
            self.get_logger().info('Lookup created successfully, user=%s, namespace=%s, lookup_file=%s', owner, namespace, lookup_name)
            
            # If the file is new, then make sure that the list is reloaded so that the editors notice the change
            lookupfiles.SplunkLookupTableFile.reload()
            
        # Edit the existing lookup otherwise
        else:
            
            # Default to nobody if the owner is None
            if owner is None:
                owner = "nobody"
                
            if namespace is None:
                # Get the namespace from the lookup file entry if we don't know it already
                namespace = lookupfiles.SplunkLookupTableFile.get(lookupfiles.SplunkLookupTableFile.build_id(lookup_name, None, owner), sessionKey=session_key).namespace
                
            
            #self.get_logger().info("filename=%s, lookup_file=%s, namespace=%s, owner=%s, key=%s", temp_file_name, lookup_name, namespace, owner, session_key)
            
            # Persist the changes from the temporary file
            lookupfiles.update_lookup_table(filename=temp_file_name, lookup_file=lookup_name, namespace=namespace, owner=owner, key=session_key)
    
    def get_or_make_sheet_if_necessary(self, google_spread_sheet, worksheet_name, rows=100, cols=20):
        """
        Create the worksheet in the given Google document if it does not exist. If it does, return it. 
        
        Args:
          google_spread_sheet_name (str): 
          worksheet_name (str): 
          rows (int, optional): Defaults to 100.
          cols (int, optional): Defaults to 20.
          
        Returns:
          The Google worksheet object
        """
        
        try:
            worksheet = google_spread_sheet.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            # Worksheet was not found, make it
            worksheet = google_spread_sheet.add_worksheet(title=worksheet_name, rows=str(rows), cols=str(cols))
            
        return worksheet