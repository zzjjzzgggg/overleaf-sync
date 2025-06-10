"""Ol Browser Login Utility"""
##################################################
# MIT License
##################################################
# File: olbrowserlogin.py
# Description: Overleaf Browser Login Utility
# Author: Moritz Glöckl
# License: MIT
# Version: 1.2.0
##################################################
from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtWebEngineCore import (QWebEnginePage, QWebEngineProfile,
                                     QWebEngineSettings)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow

# Where to get the CSRF Token and where to send the login request to
LOGIN_URL = "https://www.overleaf.com/login"
PROJECT_URL = "https://www.overleaf.com/project"  # The dashboard URL
# JS snippet to get the first link
JAVASCRIPT_EXTRACT_PROJECT_URL = "document.getElementsByClassName('dash-cell-name')[1].firstChild.href"
# JS snippet to extract the csrfToken
JAVASCRIPT_CSRF_EXTRACTOR = "document.getElementsByName('ol-csrfToken')[0].content"
# Name of the cookies we want to extract
COOKIE_NAMES = ["overleaf_session2", "GCLB", "__stripe_sid", "__stripe_mid", "oa"]
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64; rv:138.0) Gecko/20100101 Firefox/138.0"


class OlBrowserLoginWindow(QMainWindow):
    """
    Overleaf Browser Login Utility
    Opens a browser window to securely login the user and returns relevant login data.
    """

    def __init__(self, *args, **kwargs):
        super(OlBrowserLoginWindow, self).__init__(*args, **kwargs)

        self.web = QWebEngineView()

        self._cookies = {}
        self._csrf = ""
        self._login_success = False

        self.profile = QWebEngineProfile(self.web)
        self.cookie_store = self.profile.cookieStore()
        self.cookie_store.cookieAdded.connect(self.handle_cookie_added)
        self.profile.setPersistentCookiesPolicy(
            QWebEngineProfile.NoPersistentCookies)

        self.profile.settings().setAttribute(QWebEngineSettings.JavascriptEnabled,
                                             True)
        self.profile.setHttpUserAgent(USER_AGENT)

        webpage = QWebEnginePage(self.profile, self)
        self.web.setPage(webpage)
        self.web.load(QUrl.fromUserInput(LOGIN_URL))
        self.web.loadFinished.connect(self.handle_load_finished)

        self.setCentralWidget(self.web)
        self.resize(600, 700)

    def handle_load_finished(self):

        def callback(result):

            def callback(result):
                self._csrf = result
                self._login_success = True
                QCoreApplication.quit()

            self.web.load(QUrl.fromUserInput(result))
            self.web.loadFinished.connect(lambda x: self.web.page().runJavaScript(
                JAVASCRIPT_CSRF_EXTRACTOR, 0, callback))

        if self.web.url().toString() == PROJECT_URL:
            self.web.page().runJavaScript(JAVASCRIPT_EXTRACT_PROJECT_URL, 0,
                                          callback)

    def handle_cookie_added(self, cookie):
        cookie_name = cookie.name().data().decode('utf-8')
        if cookie_name in COOKIE_NAMES:
            self._cookies[cookie_name] = cookie.value().data().decode('utf-8')

    @property
    def cookies(self):
        return self._cookies

    @property
    def csrf(self):
        return self._csrf

    @property
    def login_success(self):
        return self._login_success


def login():
    from PySide6.QtCore import QLoggingCategory
    QLoggingCategory.setFilterRules('qt.webenginecontext.info=false')

    app = QApplication([])
    ol_browser_login_window = OlBrowserLoginWindow()
    ol_browser_login_window.show()
    app.exec()

    if not ol_browser_login_window.login_success:
        return None

    dat = {
        "cookie": ol_browser_login_window.cookies,
        "csrf": ol_browser_login_window.csrf
    }

    # print(dat)
    # # requesting GCLB
    # r = reqs.get(SOCKET_URL, cookies=dat["cookie"])
    # print(r.cookies)
    # dat["cookie"]['GCLB'] = r.cookies['GCLB']    # type: ignore

    return dat


if __name__ == '__main__':
    login()
