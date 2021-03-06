from flask import redirect, request, session, url_for, flash
from threading import Lock
from ConfigParser import SafeConfigParser

import globus_sdk

from vc3client import client

try:
    from urllib.parse import urlparse, urljoin
except ImportError:
    from urlparse import urlparse, urljoin

from portal import app


def load_portal_client():
    """Create an AuthClient for the portal"""
    # return globus_sdk.ConfidentialAppAuthClient(
    #     app.config['PORTAL_CLIENT_ID'], app.config['PORTAL_CLIENT_SECRET'])
    return globus_sdk.ConfidentialAppAuthClient(
        app.config['PORTAL_CLIENT_ID'], app.config['PORTAL_CLIENT_SECRET'])


def is_safe_redirect_url(target):
    """https://security.openstack.org/guidelines/dg_avoid-unvalidated-redirects.html"""  # noqa
    host_url = urlparse(request.host_url)
    redirect_url = urlparse(urljoin(request.host_url, target))

    return redirect_url.scheme in ('http', 'https') and \
        host_url.netloc == redirect_url.netloc


def get_safe_redirect():
    """https://security.openstack.org/guidelines/dg_avoid-unvalidated-redirects.html"""  # noqa
    url = request.args.get('next')
    if url and is_safe_redirect_url(url):
        return url

    url = request.referrer
    if url and is_safe_redirect_url(url):
        return url

    return '/'


def get_portal_tokens(
        scopes=['openid', 'urn:globus:auth:scope:demo-resource-server:all']):
    """
    Uses the client_credentials grant to get access tokens on the
    Portal's "client identity."
    """
    with get_portal_tokens.lock:
        if not get_portal_tokens.access_tokens:
            get_portal_tokens.access_tokens = {}

        scope_string = ' '.join(scopes)

        client = load_portal_client()
        tokens = client.oauth2_client_credentials_tokens(
            requested_scopes=scope_string)

        # walk all resource servers in the token response (includes the
        # top-level server, as found in tokens.resource_server), and store the
        # relevant Access Tokens
        for resource_server, token_info in tokens.by_resource_server.items():
            get_portal_tokens.access_tokens.update({
                resource_server: {
                    'token': token_info['access_token'],
                    'scope': token_info['scope'],
                    'expires_at': token_info['expires_at_seconds']
                }
            })

        return get_portal_tokens.access_tokens


def get_vc3_client():
    """
    Return a VC3 client instance

    :return: VC3 client instance on success
    """
    c = SafeConfigParser()
    c.readfp(open(app.config['VC3_CLIENT_CONFIG']))

    try:
        client_api = client.VC3ClientAPI(c)
        return client_api
    except Exception as e:
        app.logger.error("Couldn't get vc3 client: {0}".format(e))
        raise


get_portal_tokens.lock = Lock()
get_portal_tokens.access_tokens = None


def project_validated(name):
    """
    Checks to see if user exists within specific project

    :param name: name of project to be checked
    :return: True if user exists in project or False otherwise
    """
    vc3_client = get_vc3_client()
    # Grab project by name
    project = vc3_client.getProject(projectname=name)

    # Checks to see if user is in project
    if (session['name'] in project.members or
            session['name'] == project.owner):
        return True
    else:
        return False


def project_in_vc(name):
    """
    Checks to see if user exists within specific project associated with VC

    :param name: name of VC to be checked
    :return: True if user exists in project or False otherwise
    """
    vc3_client = get_vc3_client()
    projects = vc3_client.listProjects()
    vc = vc3_client.getRequest(requestname=name)
    vc_owner_projects = []

    for project in projects:
        if vc.owner == project.owner:
            vc_owner_projects.append(project)

    for p in vc_owner_projects:
        if (session['name'] in p.members or session['name'] == p.owner):
            return True
        else:
            return False
