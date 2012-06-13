#!/usr/bin/env python

from __future__ import print_function

import gdata.projecthosting.client
import gdata.projecthosting.data
import gdata.gauth
import gdata.client
import atom.http_core
import atom.mock_http_core
import atom.core
import gdata.data

import argparse

import json
import urllib2
import base64

description = """
Script for migrating issues from Google Code Project Hosting issue trackers to
Github issue trackers.
"""

def get_issues(client, project_name, retrieve_closed):
    """Retrieve a set of issues in a project. Returns a list of IssueEntry
    objects where the issue is not in closed state."""
    query = gdata.projecthosting.client.Query(max_results=1024 * 1024)
    feed = client.get_issues(project_name, query=query)

    out = []
    for issue in feed.entry:
        if issue.state.text == "closed" and not retrieve_closed:
            continue
        out.append(issue)
    return out


def get_comments_for_issue(client, project_name, issue_id):
    issue_id = issue_id.split('/')[-1]
    query = gdata.projecthosting.client.Query(max_results=1024 * 1024)
    comments_feed = client.get_comments(project_name, issue_id, query=query)
    out = []

    for comment in comments_feed.entry:
        theauthor = None
        for author in comment.author:
            theauthor = author.name.text
        if comment.content.text:
            out.append((theauthor,
                        comment.content.text,
                        comment.published.text))
    return out


def mark_googlecode_issue_migrated(client,
                                   author_name,
                                   project_name,
                                   issue_id,
                                   github_url):
    comment_text = "Migrated to {0}".format(github_url)
    client.update_issue(project_name,
        issue_id,
        author=author_name,
        comment=comment_text,
        status='Migrated')


def create_github_issue(title, body):
    d = {}
    d["title"] = title
    d["body"] = body
    return json.dumps(d)


def close_github_issue_json():
    d = {}
    d["state"] = "closed"
    return json.dumps(d)


def post_to_github(url, data, username, password):
    req = urllib2.Request(url, data)
    req.add_header("Authorization", "Basic "
    + base64.urlsafe_b64encode("%s:%s" % (username, password)))
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")

    f = urllib2.urlopen(req)
    response = f.read()
    return json.loads(response)


def post_issue_to_github(title, body, organization, project, user, password):
    """Create a new issue on github. Returns the number (as text) of the new
    issue."""
    uri = "https://api.github.com/repos/{0}/{1}/issues".format(organization, project)
    data = create_github_issue(title, body)
    res = post_to_github(uri, data, user, password)
    return res["number"]


def close_github_issue(issue_id, organization, project, user, password):
    """Create a new issue on github. Returns the number (as text) of the new
    issue."""
    uri = "https://api.github.com/repos/{0}/{1}/issues/{2}".format(organization, project, issue_id)
    data = close_github_issue_json()
    post_to_github(uri, data, user, password)


def build_previous_comments(comments):
    """Takes a list of tuples of (author, content, published), where they're
    all strings. Produces some HTML to append to an issue's text."""
    out = ""
    if comments:
        out = u"""<hr/><h2>earlier comments</h2>\n"""

    for (author, content, published) in comments:
        out += (u"<p><strong>{0} said, at {1}:</strong></p>\n"
                .format(author, published))
        out += u"<p>{0}</p>".format(content)
    return out


def main(args):
    ### The Google Code source project
    source_project = args['google-source']

    github_organization = args['github-organization']
    github_project = args['github-project']

    username = args['github-username']
    password = args['github-password']

    client = gdata.projecthosting.client.ProjectHostingClient()
    if args.has_key('google_username'):
        application_name = args['google_application_name']
        google_username = args['google_username']
        google_password = args['google_password']
        google_name = args['google_name']
        client.ClientLogin(google_username, google_password, source=application_name)

    migrate_closed = args['migrate_closed']
    issues = get_issues(client, source_project, migrate_closed)

    for issue in issues:
        comments = get_comments_for_issue(client, source_project, issue.id.text)
        prevcomments = build_previous_comments(comments)

        source_issue_id = issue.id.text.split('/')[-1]

        migrated_from = (
            u"<p>Migrated from http://code.google.com/p/{0}/issues/detail?id={1}</p>".
            format(source_project, source_issue_id))

        newtext = issue.content.text + migrated_from + prevcomments
        github_issue_id = post_issue_to_github(issue.title.text,
            newtext,
            github_organization,
            github_project,
            username,
            password)

        if args['migrate_closed'] and issue.state.text == "closed":
            close_github_issue(github_issue_id,
                github_organization,
                github_project,
                username,
                password)

        new_github_issue_url = ("http://github.com/{0}/{1}/issues/{2}"
                                .format(github_organization,
            github_project,
            github_issue_id))
        print("Created", new_github_issue_url)

        if args['google_mark_as_migrated']:
            mark_googlecode_issue_migrated(client,
                google_name,
                source_project,
                source_issue_id,
                new_github_issue_url)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=description)
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
