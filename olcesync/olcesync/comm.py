#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# created on 2024-04-30 17:25 by J. Zhao

# Where to get the CSRF Token and where to send the login request to
# JS snippet to get the first link
JAVASCRIPT_EXTRACT_PROJECT_URL = "document.getElementsByClassName('dash-cell-name')[1].firstChild.href"
# JS snippet to extract the csrfToken
JAVASCRIPT_CSRF_EXTRACTOR = "document.getElementsByName('ol-csrfToken')[0].content"
# Name of the cookies we want to extract
COOKIE_NAMES = ["overleaf.sid"]
