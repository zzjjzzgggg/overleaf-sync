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

from olcesync.comm import *


def on_cert_error(e):
    # print(f"cert error: {e.description()}")
    # print(f"type: {e.type()}")
    # print(f"overridable: {e.isOverridable()}")
    # print(f"url: {e.url()}")
    # for c in e.certificateChain():
    #     print(c.toText())
    e.acceptCertificate()


class OlBrowserLoginWindow(QMainWindow):
    """
    Overleaf Browser Login Utility
    Opens a browser window to securely login the user and returns relevant login data.
    """

    def __init__(self, server_ip, *args, **kwargs):
        super(OlBrowserLoginWindow, self).__init__(*args, **kwargs)

        self.webview = QWebEngineView()
        self._cookies = {}
        self._csrf = ""
        self._login_success = False

        self.LOGIN_URL = "https://{}/login".format(server_ip)
        self.PROJECT_URL = "https://{}/project".format(server_ip)

        self.profile = QWebEngineProfile(self.webview)
        self.cookie_store = self.profile.cookieStore()
        self.cookie_store.cookieAdded.connect(self.handle_cookie_added)
        self.profile.setPersistentCookiesPolicy(
            QWebEngineProfile.NoPersistentCookies)

        self.profile.settings().setAttribute(QWebEngineSettings.JavascriptEnabled,
                                             True)

        webpage = QWebEnginePage(self.profile, self)
        webpage.certificateError.connect(on_cert_error)
        self.webview.setPage(webpage)
        self.webview.load(QUrl.fromUserInput(self.LOGIN_URL))
        self.webview.loadFinished.connect(self.handle_load_finished)

        self.setCentralWidget(self.webview)
        self.resize(600, 700)

    def handle_load_finished(self):

        def callback(result):

            def callback(result):
                self._csrf = result
                self._login_success = True
                QCoreApplication.quit()

            self.webview.load(QUrl.fromUserInput(result))
            self.webview.loadFinished.connect(lambda x: self.webview.page(
            ).runJavaScript(JAVASCRIPT_CSRF_EXTRACTOR, 0, callback))

        if self.webview.url().toString() == self.PROJECT_URL:
            self.webview.page().runJavaScript(JAVASCRIPT_EXTRACT_PROJECT_URL, 0,
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


def login(server_ip):
    from PySide6.QtCore import QLoggingCategory
    QLoggingCategory.setFilterRules('''\
    qt.webenginecontext.info=false
    ''')

    app = QApplication([])
    ol_browser_login_window = OlBrowserLoginWindow(server_ip)
    ol_browser_login_window.show()
    app.exec()

    if not ol_browser_login_window.login_success:
        return None

    return {
        "cookie": ol_browser_login_window.cookies,
        "csrf": ol_browser_login_window.csrf
    }


if __name__ == '__main__':
    print(login("202.117.43.87"))
