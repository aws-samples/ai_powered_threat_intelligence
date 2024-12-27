# pylint: disable = W1514
"""
Helper module to be used in other projects to
e.g. generate qualifiers or retrieve repository information
"""

import hashlib
import json
import os
from pathlib import Path

import cdk_nag
from pygit2 import Repository


class Helper:
    """
    Helper that supports the customization of CDK l3constructs.
    """

    def __init__(
        self,
        cdk_env: str = None,
        qualifier: str = None,
        repo_name: str = None,
        branch_name: str = None,
        prefix: str = None,
        tags: dict = None,
    ):
        self.cdk_env = cdk_env
        self.qualifier = qualifier
        self.repo_name = repo_name
        self.branch_name = branch_name
        self.prefix = prefix
        self.tags = tags

    @staticmethod
    def get_repo_name_from_url(url: str) -> str:
        """
        Retrieve repository name from repository url

        :param url: git branch url
        :return: repository name
        """
        last_slash_index = max(url.rfind("/"), url.rfind("@"))
        last_suffix_index = url.rfind(".git")
        if last_suffix_index < 0:
            last_suffix_index = len(url)

        if last_slash_index < 0 or last_suffix_index <= last_slash_index:
            raise Exception(f"Badly formatted url {url}")

        return url[last_slash_index + 1 : last_suffix_index]

    def get_repo_name_from_local_git(self):
        """
        Retrieve repository name from locally selected git branch

        :return: repository name
        """
        if self.repo_name is None:
            if "REPO_NAME" in os.environ:
                self.repo_name = os.environ["REPO_NAME"]
            else:
                repo = Repository(os.getcwd())
                self.repo_name = self.get_repo_name_from_url(repo.remotes[0].url)
        return self.repo_name

    def get_branch_name_from_local_git(self) -> str:
        """
        Retrieve git branch name from currently locally selected
        branch

        :return: string git branch
        """
        if self.branch_name is None:
            if "BRANCH_NAME" in os.environ:
                self.branch_name = os.environ["BRANCH_NAME"]
            else:
                repo = Repository(os.getcwd())
                self.branch_name = repo.head.shorthand
        return self.branch_name

    def get_cdk_env(self):
        """
        Get cdk env to check the environment

        :return: environment: str
        """
        if self.cdk_env is None:
            if "CDK_ENV" in os.environ:
                self.cdk_env = os.environ["CDK_ENV"]
            else:
                self.repo_name = self.get_repo_name()
                self.branch_name = self.get_repo_branch()

        return self.cdk_env

    def calculate_qualifier(self) -> str:
        """
        Helper function to calculate hashed app name to be used as qualifier

        :return: hashed_name: str
        """
        if self.qualifier is None:
            if "QUALIFIER" in os.environ:
                self.qualifier = os.environ["QUALIFIER"]
            else:
                app_name = f"{self.get_cdk_app_name()}_{self.branch_name}"
                hashed_name = hashlib.sha256(app_name.encode()).hexdigest()[:30]
                index_first_non_numeric = hashed_name.find(next(filter(str.isalpha, hashed_name)))
                self.qualifier = hashed_name[
                    index_first_non_numeric : (10 + index_first_non_numeric)
                ]
        return self.qualifier

    def append_qualifier(self, name: str) -> str:
        """
        Append qualifier to logical id to avoid naming
        conflicts, due to multi environment setup

        :param name: logical id of CDK resource
        :return: logical id with qualifier prefix: str
        """
        if self.qualifier is None:
            self.calculate_qualifier()
        return f"{self.qualifier}-{name}"

    def get_repo_branch(self) -> str:
        """
        TODO: Update
        Set repo branch name my removing non-numeric values from qualifier
        Checks if qualifier in reserved, if so use main branch
        Replace once automation in place, that creates pipelines on branch creation
        """
        if self.branch_name is None:
            self.get_branch_name_from_local_git()
        return self.branch_name

    def get_repo_name(self) -> str:
        """
        TODO: Update
        Set repo branch name my removing non-numeric values from qualifier
        Checks if qualifier in reserved, if so use main branch
        Replace once automation in place, that creates pipelines on branch creation
        """
        if self.repo_name is None:
            self.get_repo_name_from_local_git()
        return self.repo_name

    @staticmethod
    def find_cdk(name: str, path: str):
        """
        Find a file in a given path
        :param name: file name to look for
        :param path: path in which to look for the file
        :return: returns path of the file location
        """
        for root, dirs, files in os.walk(path):
            if name in files:
                return os.path.join(root, name)

    def read_cdk_context_json(self) -> dict:
        """
        Read cdk.json context file

        :return: dict of objects read from cdk.json: dict
        """
        try:
            file_path = self.find_cdk("cdk.json", Path(__file__).absolute().parent.parent.parent)
        except FileNotFoundError:
            print("File was not found")

        with open(file_path, "r") as my_file:
            data = my_file.read()

        obj = json.loads(data)
        return obj

    def get_cdk_app_name(self) -> str:
        """
        Read cdk app name from cdk context

        :return: cdk app name: str
        """
        cdk_context = self.read_cdk_context_json()
        app_name = cdk_context.get("context").get("app-name")
        return app_name

    def get_qualifier(self) -> str:
        """
        Retrieve qualifier for this setup

        :return: qualifier: str
        """
        if self.qualifier is None:
            self.qualifier = self.calculate_qualifier()
        return self.qualifier

    def cdk_nag_add_resource_suppression(
        self, resource: any, suppression_id: str, reason: str = None, apply_to_children: bool = True
    ):
        """

        :param resource: cdk resource to apply the suppression
        :param suppression_id: cdk suppression id
        :param reason: reason for the suppression
        :param apply_to_children: apply to all children under the resource
        """
        return cdk_nag.NagSuppressions.add_resource_suppressions(
            resource,
            suppressions=[
                {
                    "id": suppression_id,
                    "reason": reason or "Default suppression by the helper, message not provided",
                }
            ],
            apply_to_children=apply_to_children,
        )
