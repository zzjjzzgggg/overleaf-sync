"""Overleaf Client"""
##################################################
# MIT License
##################################################
# File: olclient.py
# Description: Overleaf API Wrapper
# Author: Moritz Glöckl
# License: MIT
# Version: 1.2.0
##################################################

import json
import time

import requests as reqs
from bs4 import BeautifulSoup
from socketIO_client import SocketIO

# Where to get the CSRF Token and where to send the login request to
LOGIN_URL = "https://www.overleaf.com/login"
PROJECT_URL = "https://www.overleaf.com/project"    # The dashboard URL
# The URL to download all the files in zip format
DOWNLOAD_URL = "https://www.overleaf.com/project/{}/download/zip"
# UPLOAD_URL = "https://www.overleaf.com/project/{}/upload"  # The URL to upload files
UPLOAD_URL = "https://www.overleaf.com/project/{}/upload"
FOLDER_URL = "https://www.overleaf.com/project/{}/folder"    # The URL to create folders
DELETE_URL = "https://www.overleaf.com/project/{}/{}/{}"    # The URL to delete files
COMPILE_URL = "https://www.overleaf.com/project/{}/compile?enable_pdf_caching=true"    # The URL to compile the project
BASE_URL = "https://www.overleaf.com"    # The Overleaf Base URL
PATH_SEP = "/"    # Use hardcoded path separator for both windows and posix system


def search_dic(name, dic):
    """ Search `name' in dic['docs'] and dic['fileRefs']
    Return file_id and file_type
    """
    for v in dic['docs']:
        if v['name'] == name:
            return v['_id'], 'doc'
    for v in dic['fileRefs']:
        if v['name'] == name:
            return v['_id'], 'file'
    return None, None


class OverleafClient(object):
    """
    Overleaf API Wrapper
    Supports login, querying all projects, querying a specific project, downloading a project and
    uploading a file to a project.
    """

    @staticmethod
    def filter_projects(json_content, more_attrs=None):
        more_attrs = more_attrs or {}
        for p in json_content:
            if not p.get("archived") and not p.get("trashed"):
                if all(p.get(k) == v for k, v in more_attrs.items()):
                    yield p

    def __init__(self, cookie=None, csrf=None):
        self._cookie = cookie
        self._csrf = csrf

    def all_projects(self):
        """
        Get all of a user's active projects (= not archived and not trashed)
        Returns: List of project objects
        """
        projects_page = reqs.get(PROJECT_URL, cookies=self._cookie)

        json_content = json.loads(
            BeautifulSoup(
                projects_page.content,    # type: ignore
                'html.parser').find('meta', {
                    'name': 'ol-prefetchedProjectsBlob'
                }).get('content'))    # type: ignore

        return list(OverleafClient.filter_projects(json_content['projects']))

    def get_project(self, project_name):
        """
        Get a specific project by project_name
        Params: project_name, the name of the project
        Returns: project object
        """

        projects_page = reqs.get(PROJECT_URL, cookies=self._cookie)
        json_content = json.loads(
            BeautifulSoup(projects_page.content,
                          'html.parser').find('meta', {
                              'name': 'ol-prefetchedProjectsBlob'
                          }).get('content'))
        return next(
            OverleafClient.filter_projects(json_content['projects'],
                                           {"name": project_name}), None)

    def download_project(self, project_id):
        """
        Download project in zip format
        Params: project_id, the id of the project
        Returns: bytes string (zip file)
        """
        r = reqs.get(DOWNLOAD_URL.format(project_id),
                     stream=True,
                     cookies=self._cookie)
        return r.content

    def create_folder(self, project_id, parent_folder_id, folder_name):
        """
        Create a new folder in a project

        Params:
        project_id: the id of the project
        parent_folder_id: the id of the parent folder, root is the project_id
        folder_name: how the folder will be named

        Returns: folder id or None
        """

        params = {"parent_folder_id": parent_folder_id, "name": folder_name}
        headers = {"X-Csrf-Token": self._csrf}
        r = reqs.post(FOLDER_URL.format(project_id),
                      cookies=self._cookie,
                      headers=headers,
                      json=params)

        if r.ok:
            return json.loads(r.content)
        elif r.status_code == str(400):
            # Folder already exists
            return
        else:
            raise reqs.HTTPError()

    def get_project_infos(self, project_id):
        """
        Get detailed project infos about the project

        Params:
        project_id: the id of the project

        Returns: project details
        """

        project_infos = None

        # Callback function for the joinProject emitter
        def set_project_infos(project_infos_dict):
            # Set project_infos variable in outer scope
            nonlocal project_infos
            project_infos = project_infos_dict.get("project", {})

        # Convert cookie from CookieJar to string
        cookie = "GCLB={}; overleaf_session2={}".format(
            self._cookie["GCLB"], self._cookie["overleaf_session2"])

        # Connect to Overleaf Socket.IO, send a time parameter and the cookies
        socket_io = SocketIO(BASE_URL,
                             params={
                                 't': int(time.time()),
                                 'projectId': project_id
                             },
                             headers={'Cookie': cookie})

        # Wait until we connect to the socket
        socket_io.on('connect', lambda: None)
        socket_io.wait_for_callbacks()

        # Send the joinProject event and receive the project infos
        socket_io.on('joinProjectResponse', set_project_infos)
        while project_infos is None:
            socket_io.wait(1)

        # Disconnect from the socket if still connected
        if socket_io.connected:
            socket_io.disconnect()

        return project_infos

    def upload_file(self, project_id, project_infos, file_name, file_size, file):
        """
        Upload a file to the project

        Params:
        project_id: the id of the project
        file_name: how the file will be named
        file_size: the size of the file in bytes
        file: the file itself

        Returns: True on success, False on fail
        """

        # Set the folder_id to the id of the root folder
        folder_id = project_infos['rootFolder'][0]['_id']

        only_file_name = file_name

        # The file name contains path separators, check folders
        if PATH_SEP in file_name:
            # Remove last item since this is the file name
            items = file_name.split(PATH_SEP)
            local_folders, only_file_name = items[:-1], items[-1]
            # Set the current remote folder
            current_overleaf_folder = project_infos['rootFolder'][0]['folders']

            for local_folder in local_folders:
                exists_on_remote = False
                for remote_folder in current_overleaf_folder:
                    # Check if the folder exists on remote, continue with the new folder structure
                    if local_folder.lower() == remote_folder['name'].lower():
                        exists_on_remote = True
                        folder_id = remote_folder['_id']
                        current_overleaf_folder = remote_folder['folders']
                        break
                # Create the folder if it doesn't exist
                if not exists_on_remote:
                    new_folder = self.create_folder(project_id, folder_id,
                                                    local_folder)
                    current_overleaf_folder.append(new_folder)
                    folder_id = new_folder['_id']
                    current_overleaf_folder = new_folder['folders']

        # Upload the file to the predefined folder
        params = {'folder_id': folder_id}
        data = {
            "relativePath": "null",
            "name": only_file_name,
        }
        files = {"qqfile": (file_name, file)}
        headers = {
            "X-CSRF-TOKEN": self._csrf,
        }

        # Upload the file to the predefined folder
        r = reqs.post(UPLOAD_URL.format(project_id),
                      cookies=self._cookie,
                      headers=headers,
                      params=params,
                      data=data,
                      files=files)

        return r.status_code == str(200) and json.loads(r.content)["success"]

    def delete_file(self, project_id, project_infos, file_name):
        """
        Deletes a project's file

        Params:
        project_id: the id of the project
        file_name: how the file will be named

        Returns: True on success, False on fail
        """

        file_type = file_id = None
        # The file name contains path separators, check folders
        if PATH_SEP in file_name:
            items = file_name.split(PATH_SEP)
            dir_depth = len(items) - 1
            only_file_name = items[-1]
            current_overleaf_folder = project_infos['rootFolder'][0]['folders']
            for i in range(dir_depth):
                success = False
                for remote_folder in current_overleaf_folder:
                    if items[i] == remote_folder['name']:
                        if i != dir_depth - 1:
                            current_overleaf_folder = remote_folder['folders']
                        else:
                            file_id, file_type = search_dic(
                                only_file_name, remote_folder)
                        success = True
                        break
                if not success:
                    print("Local folder {} does not exist in remote!".format(
                        items[i]))
                    return False
        else:    # File is in root folder
            remote_folder = project_infos['rootFolder'][0]
            file_id, file_type = search_dic(file_name, remote_folder)

        # File not found!
        if file_id is None: return False

        headers = {"X-Csrf-Token": self._csrf}

        r = reqs.delete(DELETE_URL.format(project_id, file_type, file_id),
                        cookies=self._cookie,
                        headers=headers)

        return r.status_code == '204'

    def download_pdf(self, project_id):
        """
        Compiles and returns a project's PDF

        Params:
        project_id: the id of the project

        Returns: PDF file name and content on success
        """
        headers = {"X-Csrf-Token": self._csrf}

        body = {
            "check": "silent",
            "draft": False,
            "incrementalCompilesEnabled": True,
            "rootDoc_id": "",
            "stopOnFirstError": False
        }

        r = reqs.post(COMPILE_URL.format(project_id),
                      cookies=self._cookie,
                      headers=headers,
                      json=body)

        if not r.ok:
            raise reqs.HTTPError()

        compile_result = json.loads(r.content)

        if compile_result["status"] != "success":
            raise reqs.HTTPError()

        pdf_file = next(v for v in compile_result['outputFiles']
                        if v['type'] == 'pdf')

        download_req = reqs.get(BASE_URL + pdf_file['url'],
                                cookies=self._cookie,
                                headers=headers)

        if download_req.ok:
            return pdf_file['path'], download_req.content

        return None
