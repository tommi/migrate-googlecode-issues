#!/usr/bin/env python

from __future__ import print_function

import argparse
import json
import urllib2
import base64

import gdata.projecthosting.client
import gdata.projecthosting.data
import gdata.gauth
import gdata.client
import atom.http_core
import atom.mock_http_core
import atom.core
import gdata.data

class GoogleCode(object):
    def __init__(self, project, username, password, application_name, display_name):
        self.project = project
        self.username = username
        self.password = password
        self.application_name = application_name
        self.display_name = display_name
        self.client = gdata.projecthosting.client.ProjectHostingClient()
        if username:
            self.client.ClientLogin(username, password, source=application_name)

    def get_issues(self, retrieve_closed):
        query = gdata.projecthosting.client.Query(max_results=1024 * 1024)
        feed = self.client.get_issues(self.project, query=query)

        out = []
        for issue in feed.entry:
            if issue.state.text == "closed" and not retrieve_closed:
                continue
            out.append(issue)
        return out

    def get_comments_for_issue(self, issue_id):
        issue_id = issue_id.split('/')[-1]
        query = gdata.projecthosting.client.Query(max_results=1024 * 1024)
        comments_feed = self.client.get_comments(self.project, issue_id, query=query)
        comments = []

        for comment in comments_feed.entry:
            theauthor = None
            for author in comment.author:
                theauthor = author.name.text
            if comment.content.text:
                comments.append((theauthor,
                                 comment.content.text,
                                 comment.published.text))
        return self._format_comments(comments)

    def _format_comments(self, comments):
        out = ""
        if comments:
            out = u"""<hr/><h2>earlier comments</h2>\n"""

        for (author, content, published) in comments:
            out += (u"<p><strong>{0} said, at {1}:</strong></p>\n"
                    .format(author, published))
            out += u"<p>{0}</p>".format(content)
        return out

    def mark_googlecode_issue_migrated(self, issue_id, github_url):
        comment_text = "Migrated to {0}".format(github_url)
        self.client.update_issue(self.project,
            issue_id,
            author=self.display_name,
            comment=comment_text,
            status='Migrated')
        print("Marked as migrated", issue_id)

    def get_url(self, issue_id):
        return u"http://code.google.com/p/{0}/issues/detail?id={1}".format(self.project, issue_id)


class Github(object):
    def __init__(self, organization, project, username, password):
        self.organization = organization
        self.project = project
        self.username = username
        self.password = password

    def create_issue(self, source_url, title, body):
        uri = "https://api.github.com/repos/{0}/{1}/issues".format(self.organization, self.project)
        data = self._create_github_issue_json(title, body)
        res = self._post_to_github(uri, data)
        issue_id = res["number"]
        print("Migrated {0} => {1}".format(source_url, self._get_url(issue_id)))
        return issue_id

    def _create_github_issue_json(self, title, body):
        d = {}
        d["title"] = title
        d["body"] = body
        return json.dumps(d)

    def _post_to_github(self, url, data):
        req = urllib2.Request(url, data)
        req.add_header("Authorization", "Basic " + base64.urlsafe_b64encode("%s:%s" % (self.username, self.password)))
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")

        f = urllib2.urlopen(req)
        response = f.read()
        return json.loads(response)

    def _get_url(self, issue_id):
        return "http://github.com/{0}/{1}/issues/{2}".format(self.organization, self.project, issue_id)

    def close_github_issue(self, issue_id):
        uri = "https://api.github.com/repos/{0}/{1}/issues/{2}".format(self.organization, self.project, issue_id)
        data = self._close_github_issue_json()
        self._post_to_github(uri, data)
        print("Closed", self._get_url(issue_id))

    def _close_github_issue_json(self):
        d = {}
        d["state"] = "closed"
        return json.dumps(d)


def create_new_issue_content(googlecode, issue, source_issue_id):
    issue_comments = googlecode.get_comments_for_issue(issue.id.text)
    issue_content = issue.content.text
    migrated_from = u"<p>Migrated from {0}</p>".format(googlecode.get_url(source_issue_id))
    new_content = issue_content + migrated_from + issue_comments
    return new_content


def main(args):
    googlecode = GoogleCode(args.get('google-source'),
        args.get('google_username'),
        args.get('google_password'),
        args.get('google_application_name'),
        args.get('google_name'))

    github = Github(args.get('github-organization'),
        args.get('github-project'),
        args.get('github-username'),
        args.get('github-password'))

    migrate_closed = args['migrate_closed']
    issues = googlecode.get_issues(migrate_closed)

    for issue in issues:
        source_issue_id = issue.id.text.split('/')[-1]
        new_content = create_new_issue_content(googlecode, issue, source_issue_id)
        github_issue_id = github.create_issue(googlecode.get_url(source_issue_id), issue.title.text, new_content)

        if args.get('migrate_closed') and issue.state.text == "closed":
            github.close_github_issue(github_issue_id)

        if args.get('google_mark_as_migrated'):
            googlecode.mark_googlecode_issue_migrated(source_issue_id, new_github_issue_url)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrating issues from Google Code Project Hosting to Github")
    parser.add_argument('google-source', help='Google code source project')
    parser.add_argument('github-organization', help='Github organization')
    parser.add_argument('github-project', help='Github project')
    parser.add_argument('github-username', help='Github username')
    parser.add_argument('github-password', help='Github password')
    parser.add_argument('--google-username', help='Google username')
    parser.add_argument('--google-password', help='Google password')
    parser.add_argument('--google-name', help='Google display name')
    parser.add_argument('--google-application-name', help='Google application name')
    parser.add_argument('--google-mark-as-migrated', type=bool, default=False, help="Mark as migrated on googlecode")
    parser.add_argument('--migrate-closed', type=bool, default=False, help="Migrate also closed issues")

    main(vars(parser.parse_args()))
