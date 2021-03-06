#### PATTERN | WEB ###################################################################################
# Copyright (c) 2010 University of Antwerp, Belgium
# Author: Tom De Smedt <tom@organisms.be>
# License: BSD (see LICENSE.txt for details).
# http://www.clips.ua.ac.be/pages/pattern

######################################################################################################
# Python API interface for various web services (Google, Twitter, Wikipedia, ...)

import threading
import time
import os
import socket, urlparse, urllib, urllib2
import htmlentitydefs
import sgmllib
import re
import xml.dom.minidom
import json
import bisect

try:
    # Import persistent Cache.
    # If this module is used separately, a dict is used (i.e. for this Python session only).
    from cache import Cache, cache
except:
    cache = {}

try:
    from imap import Mail, MailFolder, Message, GMAIL
    from imap import MailError, MailServiceError, MailLoginError, MailNotLoggedIn
    from imap import FROM, SUBJECT, DATE, BODY, ATTACHMENTS
except:
    pass
    
try:
    MODULE = os.path.dirname(os.path.abspath(__file__))
except:
    MODULE = ""

#### UNICODE #########################################################################################
    
def decode_utf8(string):
    """ Returns the given string as a unicode string (if possible).
    """
    if isinstance(string, str):
        try: 
            return string.decode("utf-8")
        except:
            return string
    return unicode(string)
    
def encode_utf8(string):
    """ Returns the given string as a Python byte string (if possible).
    """
    if isinstance(string, unicode):
        try: 
            return string.encode("utf-8")
        except:
            return string
    return str(string)

u = decode_utf8
s = encode_utf8

# For clearer source code:
bytestring = s


#### ASYNCHRONOUS REQUEST ############################################################################

class AsynchronousRequest:
    
    def __init__(self, function, *args, **kwargs):
        """ Executes the function in the background.
            AsynchronousRequest.done is False as long as it is busy, but the program will not halt in the meantime.
            AsynchronousRequest.value contains the function's return value once done.
            AsynchronousRequest.error contains the Exception raised by an erronous function.
            For example, this is useful for running live web requests while keeping an animation running.
            For good reasons, there is no way to interrupt a background process (i.e. Python thread).
            You are responsible for ensuring that the given function doesn't hang.
        """
        self._response = None # The return value of the given function.
        self._error    = None # The exception (if any) raised by the function.
        self._time     = time.time()
        self._function = function
        self._thread   = threading.Thread(target=self._fetch, args=(function,)+args, kwargs=kwargs)
        self._thread.start()
        
    def _fetch(self, function, *args, **kwargs):
        try: 
            self._response = function(*args, **kwargs)
        except Exception, e:
            self.error = e

    def now(self):
        """ Waits for the function to finish and yields its return value.
        """
        self._thread.join(); return self._response

    @property
    def elapsed(self):
        return time.time() - self._time
    @property
    def done(self):
        return not self._thread.isAlive()
    @property
    def value(self):
        return self._response
    @property
    def error(self):
        return self._error
        
    def __repr__(self):
        return "AsynchronousRequest(function='%s')" % self._function.__name__

def asynchronous(function, *args, **kwargs):
    return AsynchronousRequest(function, *args, **kwargs)
send = asynchronous

#### URL #############################################################################################

# User agent and referrer.
# Used to identify the application accessing the web.
USER_AGENT = "Pattern/1.0 +http://www.clips.ua.ac.be/pages/pattern"
REFERRER   = "http://www.clips.ua.ac.be/pages/pattern"

# Mozilla user agent.
# Websites can include code to block out any application except browsers.
MOZILLA = "Mozilla/5.0"

# HTTP request method.
GET  = "get"  # Data is encoded in the URL.
POST = "post" # Data is encoded in the message body.

# URL parts.
# protocol://username:password@domain:port/path/page?query_string#anchor
PROTOCOL, USERNAME, PASSWORD, DOMAIN, PORT, PATH, PAGE, QUERY, ANCHOR = \
    "protocol", "username", "password", "domain", "port", "path", "page", "query", "anchor"

# MIME type.
MIMETYPE_WEBPAGE    = ["text/html"]
MIMETYPE_STYLESHEET = ["text/css"]
MIMETYPE_PLAINTEXT  = ["text/plain"]
MIMETYPE_PDF        = ["application/pdf"]
MIMETYPE_NEWSFEED   = ["application/rss+xml", "application/atom+xml"]
MIMETYPE_IMAGE      = ["image/gif", "image/jpeg", "image/x-png"]
MIMETYPE_AUDIO      = ["audio/mpeg", "audio/x-aiff", "audio/x-wav"]
MIMETYPE_VIDEO      = ["video/mpeg", "video/quicktime"]
MIMETYPE_ARCHIVE    = ["application/x-stuffit", "application/x-tar", "application/zip"]

def extension(filename):
    return os.path.splitext(filename)[1]

def urldecode(query):
    """ Inverse operation of urllib.urlencode.
        Returns a dictionary of (name, value)-items from a URL query string.
    """
    query = [(kv.split("=")+[None])[:2] for kv in query.split("&")]
    query = [(urllib.unquote_plus(bytestring(k)), urllib.unquote_plus(bytestring(v))) for k,v in query]
    query = [(u(k), u(v)) for k,v in query]
    query = [(k, v.isdigit() and int(v) or v) for k,v in query]
    query = dict([(k,v) for k,v in query if k!=""])
    return query
    
url_decode = urldecode

def proxy(host, protocol="https"):
    """ Returns the value for the URL.open() proxy parameter.
        - host: host address of the proxy server.
    """
    return (host, protocol)

class URLError(Exception):
    pass # URL contains errors (e.g. a missing t in htp://).
class URLTimeout(URLError):
    pass # URL takes to long to load.
class HTTPError(URLError):
    pass # URL causes an error on the contacted server.
class HTTP400BadRequest(HTTPError):
    pass # URL contains an invalid request.
class HTTP401Authentication(HTTPError):
    pass # URL requires a login and password.
class HTTP403Forbidden(HTTPError):
    pass # URL is not accessible (user-agent?)
class HTTP404NotFound(HTTPError):
    pass # URL doesn't exist on the internet.
class HTTP420Error(HTTPError):
    pass # Used by Twitter for rate limiting.
class HTTP301Redirect(HTTPError):
    pass # Too many redirects.
         # The site may be trying to set a cookie and waiting for you to return it,
         # or taking other measures to discern a browser from a script.
         # For specific purposes you should build your own urllib2.HTTPRedirectHandler
         # and pass it to urllib2.build_opener() in URL.open()
    
class URL:
    
    def __init__(self, string=u"", method=GET, query={}):
        """ URL object with the individual parts available as attributes:
            For protocol://username:password@domain:port/path/page?query_string#anchor:
            - URL.protocol: http, https, ftp, ...
            - URL.username: username for restricted domains.
            - URL.password: password for restricted domains.
            - URL.domain  : the domain name, e.g. nodebox.net.
            - URL.port    : the server port to connect to.
            - URL.path    : the server path of folders, as a list, e.g. ['news', '2010']
            - URL.page    : the page name, e.g. page.html.
            - URL.query   : the query string as a dictionary of (name, value)-items.
            - URL.anchor  : the page anchor.
            If method is POST, the query string is sent with HTTP POST.
        """
        self.__dict__["method"]    = method # Use __dict__ directly since __setattr__ is overridden.
        self.__dict__["_string"]   = u(string)
        self.__dict__["_parts"]    = None
        self.__dict__["_headers"]  = None
        self.__dict__["_redirect"] = None
        if isinstance(string, URL):
            self.__dict__["method"] = string.method
            self.query.update(string.query)
        if len(query) > 0:
            # Requires that we parse the string first (see URL.__setattr__).
            self.query.update(dict([(u(k),u(v)) for k,v in query.items()]))
        
    def _parse(self):
        """ Parses all the parts of the URL string to a dictionary.
            URL format: protocal://username:password@domain:port/path/page?querystring#anchor
            For example: http://user:pass@example.com:992/animal/bird?species=seagull&q#wings
            This is a cached method that is only invoked when necessary, and only once.
        """
        p = urlparse.urlsplit(self._string)
        P = {PROTOCOL : p[0],            # http
             USERNAME : u"",             # user
             PASSWORD : u"",             # pass
               DOMAIN : p[1],            # example.com
                 PORT : u"",             # 992
                 PATH : p[2],            # [animal]
                 PAGE : u"",             # bird
                QUERY : urldecode(p[3]), # {"species": "seagull", "q": None}
               ANCHOR : p[4]             # wings
        }
        # Split the username and password from the domain.
        if "@" in P[DOMAIN]:
            P[USERNAME], \
            P[PASSWORD] = (p[1].split("@")[0].split(":")+[u""])[:2]
            P[DOMAIN]   =  p[1].split("@")[1]
        # Split the port number from the domain.
        if ":" in P[DOMAIN]:
            P[DOMAIN], \
            P[PORT] = P[DOMAIN].split(":")
            P[PORT] = int(P[PORT])
        # Split the base page from the path.
        if "/" in P[PATH]:
            P[PAGE] = p[2].split("/")[-1]
            P[PATH] = p[2][:len(p[2])-len(P[PAGE])].strip("/").split("/")
            P[PATH] = filter(lambda v: v != "", P[PATH])
        else:
            P[PAGE] = p[2].strip("/")
            P[PATH] = []
        self.__dict__["_parts"] = P
    
    # URL.string yields unicode(URL) by joining the different parts,
    # if the URL parts have been modified.
    def _get_string(self): return unicode(self)
    def _set_string(self, v):
        self.__dict__["_string"] = u(v)
        self.__dict__["_parts"]  = None
    string = property(_get_string, _set_string)
    
    @property
    def parts(self):
        if not self._parts: self._parse()
        return self._parts
    
    def __getattr__(self, k):
        if k in self.__dict__ : return self.__dict__[k]
        if k in self.parts    : return self.__dict__["_parts"][k]
        raise AttributeError, "'URL' object has no attribute '%s'" % k
    
    def __setattr__(self, k, v):
        if k in self.__dict__ : self.__dict__[k] = u(v); return
        if k in self.parts    : self.__dict__["_parts"][k] = u(v); return
        raise AttributeError, "'URL' object has no attribute '%s'" % k
        
    def open(self, timeout=10, proxy=None, user_agent=USER_AGENT, referrer=REFERRER):
        """ Returns a connection to the url from which data can be retrieved with connection.read().
            When the timeout amount of seconds is exceeded, raises a URLTimeout.
            When an error occurs, raises a URLError (e.g. HTTP404NotFound).
        """
        url = self.string
        # Use basic urllib.urlopen() instead of urllib2.urlopen() for local files.
        if os.path.exists(url):
            return urllib.urlopen(url)
        # Get the query string as a separate parameter if method=POST.          
        post = self.method == POST and urllib.urlencode(bytestring(self.query)) or None
        socket.setdefaulttimeout(timeout)
        if proxy:
            proxy = urllib2.ProxyHandler({proxy[1]: proxy[0]})
            proxy = urllib2.build_opener(proxy, urllib2.HTTPHandler)
            urllib2.install_opener(proxy)
        try:
            request = urllib2.Request(url, post, {"User-Agent": user_agent, "Referer": referrer})
            return urllib2.urlopen(request)
        except urllib2.HTTPError, e:
            if e.code == 400: raise HTTP400BadRequest
            if e.code == 401: raise HTTP401Authentication
            if e.code == 403: raise HTTP403Forbidden
            if e.code == 404: raise HTTP404NotFound
            if e.code == 420: raise HTTP420Error
            if e.code == 301: raise HTTP301Redirect
            raise HTTPError
        except urllib2.URLError, e:
            if e.reason[0] in (36, "timed out"): raise URLTimeout
            raise URLError
        except ValueError:
            raise URLError
            
    def download(self, timeout=10, cached=True, throttle=0, proxy=None, user_agent=USER_AGENT, referrer=REFERRER):
        """ Downloads the content at the given URL (by default it will be cached locally).
            The content is returned as a unicode string.
        """
        id  = (self._parts is None and self.method == GET) and self._string or repr(self.parts)
        if cached and id in cache:
            return cache[id]
        t = time.time()
        # Open a connection with the given settings, read it and (by default) cache the data.
        data = self.open(timeout, proxy, user_agent, referrer).read()
        data = u(data)
        if cached:
            cache[id] = data
        if not cached and throttle:
            time.sleep(max(throttle-(time.time()-t), 0))
        return data
            
    @property
    def exists(self, timeout=10):
        """ Yields False if the URL generates a HTTP404NotFound error.
        """
        try: self.open(timeout)
        except HTTP404NotFound:
            return False
        except HTTPError, URLTimeoutError:
            return True
        except URLError:
            return False
        except:
            return True
        return True
    
    @property
    def mimetype(self, timeout=10):
        """ Yields the MIME-type of the document at the URL, or None.
            MIME is more reliable than simply checking the document extension.
            You can then do: URL.mimetype in MIMETYPE_IMAGE.
        """
        try: 
            return self.headers["content-type"].split(";")[0]
        except KeyError:
            return None
            
    @property
    def headers(self, timeout=10):
        """ Yields a dictionary with the HTTP response headers.
        """
        if self.__dict__["_headers"] is None:
            try:
                h = dict(self.open(timeout).info())
            except URLError:
                h = {}
            self.__dict__["_headers"] = h
        return self.__dict__["_headers"]
            
    @property
    def redirect(self, timeout=10):
        """ Yields the redirected URL, or None.
        """
        if self.__dict__["_redirect"] is None:
            try:
                r = self.open(timeout).geturl()
            except URLError:
                r = None
            self.__dict__["_redirect"] = r != self.string and r or ""
        return self.__dict__["_redirect"] or None

    def __str__(self):
        return bytestring(self.string)
            
    def __unicode__(self):
        # The string representation includes the query attributes with HTTP GET.
        # This gives us the advantage of not having to parse the URL
        # when no separate query attributes were given (e.g. all info is in URL._string):
        if self._parts is None and self.method == GET: 
            return self._string
        P = self._parts 
        Q = dict([(bytestring(k), bytestring(v)) for k,v in P[QUERY].items()])
        u = []
        if P[PROTOCOL]: u.append("%s://" % P[PROTOCOL])
        if P[USERNAME]: u.append("%s:%s@" % (P[USERNAME], P[PASSWORD]))
        if P[DOMAIN]  : u.append(P[DOMAIN])
        if P[PORT]    : u.append(":%s" % P[PORT])
        if P[PATH]    : u.append("/%s/" % "/".join(P[PATH]))
        if P[PAGE]    : u.append("/%s" % P[PAGE]); u[-2]=u[-2].rstrip("/")
        if self.method == GET: u.append("?%s" % urllib.urlencode(Q))
        if P[ANCHOR]  : u.append("#%s" % P[ANCHOR])
        return u"".join(u)

    def __repr__(self):
        return "URL('%s', method='%s')" % (str(self), str(self.method))

    def copy(self):
        return URL(self.string, self.method, self.query)

#url = URL("http://user:pass@example.com:992/animal/bird?species#wings")
#print url.parts
#print url.string

#--- FIND URLs ---------------------------------------------------------------------------------------

RE_URL_HEAD = r"[\s|\(\>]"                                         # Preceded by space, parenthesis or HTML tag.
RE_URL_TAIL = r"[%s]*[\s|\<]" % "|".join(".,)")                    # Followed by space, punctuation or HTML tag.
RE_URL1 = r"(https?://.*?)" + RE_URL_TAIL                          # Starts with http:// or https://
RE_URL2 = RE_URL_HEAD + r"(www\..*?\..*?)" + RE_URL_TAIL           # Starts with www.
RE_URL3 = RE_URL_HEAD + r"([\w|-]*?\.(com|net|org))" + RE_URL_TAIL # Ends with .com, .net, .org

RE_URL1, RE_URL2, RE_URL3 = \
    re.compile(RE_URL1), re.compile(RE_URL2), re.compile(RE_URL3)

def find_urls(string, unique=True):
    """ Returns a list of URLs parsed from the string.
        Works on http://, https://, www. links or domain names ending in .com, .org, .net.
        Links can be preceded by leading punctuation (open parens)
        and followed by trailing punctuation (period, comma, close parens).
    """
    string = u(string).replace(u"\u2024", ".")
    matches = []
    for p in (RE_URL1, RE_URL2, RE_URL3):
        for m in p.finditer(" %s " % string):
            s = m.group(1)
            i = m.start()
            if s.endswith(("'","\"",">")) and i >= 7 and string[i-7:i-2].lower() == "href=":
                # For <a href="http://google.com">,
                # the link is http://google.com and not http://google.com">
                s = s.rstrip("\"'>")
            #if not s.lower().startswith("http"):
            #    s = "http://" + s
            if not unique or s not in matches:
                matches.append(s)
    return matches
    
links = find_urls

#### PLAIN TEXT ######################################################################################

BLOCK = [
    "title", "h1", "h2", "h3", "h4", "h5", "h6", "p", 
    "center", "blockquote", "div", "table", "ul", "ol", "pre", "code", "form"
]

# Element tag replacements for a stripped version of HTML source with strip_tags().
# Block-level elements are followed by linebreaks,
# list items are preceded by an asterisk ("*").
LIST_ITEM = "*"
blocks = dict.fromkeys(BLOCK+["br","tr","td"], ("", "\n\n"))
blocks.update({
    "li": ("%s " % LIST_ITEM, "\n"),
    "th": ("", "\n"),
    "tr": ("", "\n"),
    "td": ("", "\t"),
})

class SGMLParser(sgmllib.SGMLParser):
    
    def __init__(self):
        sgmllib.SGMLParser.__init__(self)
        
    def clean(self, html):
        html = decode_utf8(html)
        html = html.replace("/>", " />")
        html = html.replace("  />", " />")
        html = html.replace("<!", "&lt;!")
        html = html.replace("&lt;!DOCTYPE", "<!DOCTYPE")
        html = html.replace("&lt;!doctype", "<!doctype")
        html = html.replace("&lt;!--", "<!--")
        return html
    
    def convert_charref(self, name):
        # This fixes a bug in older versions of sgmllib when working with Unicode.
        # Fix: ASCII ends at 127, not 255
        try: n = int(name)
        except ValueError:
            return
        if not 0 <= n <= 127:
            return
        return self.convert_codepoint(n)

class HTMLTagstripper(SGMLParser):
    
    def __init__(self):
        SGMLParser.__init__(self)

    def strip(self, html, exclude=[], replace=blocks):
        """ Returns the HTML string with all element tags (e.g. <p>) removed.
            - exclude    : a list of tags to keep. Element attributes are stripped.
                           To preserve attributes a dict of (tag name, [attribute])-items can be given.
            - replace    : a dictionary of (tag name, (replace_before, replace_after))-items.
                           By default, block-level elements are separated with linebreaks.
            - whitespace : keep the original whitespace from the input string?
        """
        if html is None:
            return None
        self._exclude = isinstance(exclude, dict) and exclude or dict.fromkeys(exclude, [])
        self._replace = replace
        self._data    = []
        self.feed(self.clean(html))
        self.close()
        self.reset()
        return "".join(self._data)
    
    def unknown_starttag(self, tag, attributes):
        if tag in self._exclude:
            # Create the tag attribute string, 
            # including attributes defined in the HTMLTagStripper._exclude dict.
            a = len(self._exclude[tag]) > 0 and attributes or []
            a = ["%s=\"%s\"" % (k,v) for k,v in a if k in self._exclude[tag]]
            a = (" "+" ".join(a)).rstrip()
            self._data.append("<%s%s>" % (tag, a))
        if tag in self._replace: 
            self._data.append(self._replace[tag][0])
            
    def unknown_endtag(self, tag):
        if tag in self._exclude and self._data and self._data[-1].startswith("<"+tag):
            # Never keep empty elements (e.g. <a></a>).
            self._data.pop(-1); return
        if tag in self._exclude:
            self._data.append("</%s>" % tag)
        if tag in self._replace: 
            self._data.append(self._replace[tag][1])

    def handle_data(self, data):
	    self._data.append(data.strip("\n\t"))
    def handle_entityref(self, ref):
        self._data.append("&%s;" % ref)
    def handle_charref(self, ref):
        self._data.append("&%s;" % ref)

# As a function:
strip_tags = HTMLTagstripper().strip

def strip_element(string, tag, attributes=""):
    """ Removes all elements with the given tagname and attributes from the string.
        Open and close tags are kept in balance.
        No HTML parser is used: strip_element(s, "a", "href='foo' class='bar'")
        matches "<a href='foo' class='bar'" but not "<a class='bar' href='foo'".
    """
    t, i, j = tag.strip("</>"), 0, 0
    while j >= 0:
        i = string.find("<%s%s" % (t, (" "+attributes.strip()).rstrip()), i)
        j = string.find("</%s>" % t, i+1)
        opened, closed = string[i:j].count("<%s" % t), 1
        while opened > closed and j >= 0:
            k = string.find("</%s>" % t, j+1)
            opened += string[j:k].count("<%s" % t)
            closed += 1
            j = k
        if i < 0: return string
        if j < 0: return string[:i]
        string = string[:i] + string[j+len(t)+3:]
    return string

def strip_between(a, b, string):
    """ Removes anything between (and including) string a and b inside the given string.
    """
    p = "%s.*?%s" % (a, b)
    p = re.compile(p, re.DOTALL | re.I)
    return re.sub(p, "", string)
    
def strip_javascript(html): 
    return strip_between("<script.*?>", "</script>", html)
def strip_inline_css(html): 
    return strip_between("<style.*?>", "</style>", html)
def strip_comments(html): 
    return strip_between("<!--", "-->", html)
def strip_forms(html): 
    return strip_between("<form.*?>", "</form>", html)

RE_UNICODE   = re.compile(r'&(#?)(x?)(\w+);') # &#201;
RE_AMPERSAND = re.compile(r"\&(?!\#)")        # & not followed by #

def decode_entities(string):
    # From: http://snippets.dzone.com/posts/show/4569
    def _replace_entity(match):
        entity = match.group(3)
        if match.group(1) == "#"\
        or entity.isdigit(): # Catch &39; and &160; where we'd expect &#39; and &#160;
            if match.group(2) == '' : return unichr(int(entity))
            if match.group(2) == 'x': return unichr(int('0x'+entity, 16))
        else:
            cp = htmlentitydefs.name2codepoint.get(entity)
            return cp and unichr(cp) or match.group()
    if isinstance(string, basestring):
        return RE_UNICODE.subn(_replace_entity, string)[0]
    else:
        return string

def encode_entities(string):
    string = RE_AMPERSAND.sub("&amp;", string) # & not followed by #
    string = string.replace("<", "&lt;")
    string = string.replace(">", "&gt;")
    string = string.replace('"', "&quot;")
    string = string.replace("'", "&#39;")
    return string

RE_SPACES = re.compile(r" +",  re.MULTILINE) # Matches one or more spaces.
RE_TABS   = re.compile(r"\t+", re.MULTILINE) # Matches one or more tabs.

def collapse_spaces(string):
    """ Returns a string with consecutive spaces collapsed to a single space.
    """
    return RE_SPACES.sub(" ", string).strip(" ")

def collapse_linebreaks(string, threshold=1):
    """ Returns a string with consecutive linebreaks collapsed to at most the given threshold.
        Whitespace on empty lines and at the end of each lines is removed.
    """
    n = "\n" * threshold
    p = [s.rstrip() for s in string.replace("\r", "").split("\n")]
    string = "\n".join(p)
    string = re.sub(n+r"+", n, string)
    return string

def collapse_tabs(string, indentation=False):
    """ Returns a string with (consecutive) tabs replaced by a single space.
        With indentation=True, retains leading tabs on each line.
    """
    p = []
    for x in string.splitlines():
        n = indentation and len(x) - len(x.lstrip("\t")) or 0
        p.append("\t"*n + RE_TABS.sub(" ", x).strip(" "))
    return "\n".join(p)
    
def plaintext(html, keep=[], replace=blocks, linebreaks=2, indentation=False):
    """ Returns a string with all HTML tags removed.
        Content inside HTML comments, the <style> tag and the <script> tags is removed.
        - keep        : a list of tags to keep. Element attributes are stripped.
                        To preserve attributes a dict of (tag name, [attribute])-items can be given.
        - replace     : a dictionary of (tag name, (replace_before, replace_after))-items.
                        By default, block-level elements are followed by linebreaks.
        - linebreaks  : the maximum amount of consecutive linebreaks,
        - indentation : keep tabs?
    """
    html = html.replace("\r", "\n")
    html = strip_javascript(html)
    html = strip_inline_css(html)
    html = strip_comments(html)
    html = strip_forms(html)
    html = strip_tags(html, exclude=keep, replace=replace)
    html = decode_entities(html)
    html = collapse_spaces(html)
    html = collapse_linebreaks(html, linebreaks)
    html = collapse_tabs(html, indentation)
    html = html.strip()
    return html

#### SEARCH ENGINE ###################################################################################

SEARCH    = "search"    # Query for pages (i.e. links to websites).
IMAGE     = "image"     # Query for images.
NEWS      = "news"      # Query for news items.
BLOG      = "blog"      # Query for blog posts.
TRENDS    = "trend"     # Query for trend words (in use on Twitter).

TINY      = "tiny"      # Image size around 100x100.
SMALL     = "small"     # Image size around 200x200.
MEDIUM    = "medium"    # Image size around 500x500.
LARGE     = "large"     # Image size around 1000x1000.

RELEVANCY = "relevancy" # Sort results by most relevant.
LATEST    = "latest"    # Sort results by most recent.

class Result(dict):
    
    def __init__(self, url):
        """ An item in a list of results returned by SearchEngine.search().
            All dictionary entries are available as unicode string attributes.
            - url        : the URL of the referred web content,
            - title      : the title of the content at the URL,
            - description: the content description,
            - language   : the content language,
            - author     : for news items and images, the author,
            - date       : for news items, the publication date.
        """
        dict.__init__(self)
        self.url   = url

    def download(self, *args, **kwargs):
        """ Download the content at the given URL. 
            By default it will be cached - see URL.download().
        """
        return URL(self.url).download(*args, **kwargs)

    def __getattr__(self, k):
        return self.get(k, u"")
    def __getitem__(self, k):
        return self.get(k, u"")
    def __setattr__(self, k, v):
        dict.__setitem__(self, u(k), v is not None and u(v) or u"") # Store strings as unicode.
    def __setitem__(self, k, v):
        dict.__setitem__(self, u(k), v is not None and u(v) or u"")
        
    def setdefault(self, k, v):
        dict.setdefault(self, u(k), u(v))
    def update(self, *args, **kwargs):
        map = dict()
        map.update(*args, **kwargs)
        dict.update(self, [(u(k), u(v)) for k,v in map.items()])

    def __repr__(self):
        return "Result(url=%s)" % repr(self.url)

class Results(list):
    
    def __init__(self, source=None, query=None, type=SEARCH, total=0):
        """ A list of results returned from SearchEngine.search().
            - source: the service that yields the results (e.g. GOOGLE, TWITTER).
            - query : the query that yields the results.
            - type  : the query type (SEARCH, IMAGE, NEWS, BLOG, TREND).
            - total : the total result count.
                      This is not the length of the list, but the total number of matches for the given query.
        """
        self.source = source
        self.query  = query
        self.type   = type
        self.total  = total

class SearchEngine:
    
    def __init__(self, license=None, throttle=0.1):
        """ A base class for a web service.
            - license  : license key for the API,
            - throttle : delay between requests (avoid hammering the server).
            Inherited by: Google, Yahoo, Bing, Twitter, Wikipedia, Flickr.
        """
        self.license  = license
        self.throttle = throttle    # Amount of sleep time after executing a query.
        self.format   = lambda x: x # Formatter applied to each attribute of each Result.
    
    def search(self, query, type=SEARCH, start=1, count=10, sort=RELEVANCY, size=None, cached=True, **kwargs):
        return Results(source=None, query=query, type=type)

class SearchEngineError(HTTPError):
    pass
class SearchEngineTypeError(SearchEngineError):
    pass # Raised when an unknown type is passed to SearchEngine.search().
class SearchEngineLimitError(SearchEngineError):
    pass # Raised when the query limit for a license is reached.

#--- GOOGLE ------------------------------------------------------------------------------------------
# http://code.google.com/apis/ajaxsearch/signup.html
# http://code.google.com/apis/ajaxsearch/documentation/

GOOGLE = "http://ajax.googleapis.com/ajax/services/"
GOOGLE_LICENSE = "ABQIAAAAsHTxlz1n7jNlYECDj_EF1BT1NOe6bJHqZiq60f1JJ3OzEzDM5BQcAozHwWvFrwx2DDlP6xlTRnS6Cw"

# Search result descriptions can start with: "Jul 29, 2007 ...",
# which is the date of the page parsed by Google from the content.
RE_GOOGLE_DATE = re.compile("([A-Z][a-z]{2} [0-9]{1,2}, [0-9]{4}) <b>...</b> ")

class Google(SearchEngine):
    
    def __init__(self, license=None, throttle=0.1):
        SearchEngine.__init__(self, license or GOOGLE_LICENSE, throttle)
    
    def search(self, query, type=SEARCH, start=1, count=8, sort=RELEVANCY, size=None, cached=True, **kwargs):
        """ Returns a list of results from Google for the given query.
            - type : SEARCH, IMAGE, NEWS or BLOG,
            - start: maximum 64 results => start 1-7 with count=8,
            - count: 8,
            - size : for images, either TINY, SMALL, MEDIUM, LARGE or None.
            There is no daily limit.
        """
        url = GOOGLE
        if   type == SEARCH : url += "search/web?"
        elif type == IMAGE  : url += "search/images?"
        elif type == NEWS   : url += "search/news?"
        elif type == BLOG   : url += "search/blogs?"
        else:
            raise SearchEngineTypeError
        if not query or count < 1 or start >= 8: 
            return Results(GOOGLE, query, type)
        url = URL(url, method=GET, query={
             "key" : self.license or "",
               "v" : 1.0,
               "q" : query,
           "start" : 1 + (start-1) * 8,
             "rsz" : "large",
           "imgsz" : { TINY : "small", 
                      SMALL : "medium", 
                     MEDIUM : "large", 
                      LARGE : "xlarge" }.get(size, "")
        })
        kwargs.setdefault("throttle", self.throttle)
        data = url.download(cached=cached, **kwargs)
        data = json.loads(data)
        data = data.get("responseData") or {}
        results = Results(GOOGLE, query, type)
        results.total = int(data.get("cursor", {}).get("estimatedResultCount") or 0)
        for x in data.get("results", []):
            r = Result(url=None)
            r.url         = self.format(x.get("url", x.get("blogUrl")))
            r.title       = self.format(x.get("title"))
            r.description = self.format(x.get("content"))
            r.date        = self.format(x.get("publishedDate"))
            r.author      = self.format(x.get("publisher", x.get("author"))) 
            r.author      = r.author != "unknown" and r.author or None
            if not r.date:
                # Google Search descriptions can start with a date (parsed from the content):
                m = RE_GOOGLE_DATE.match(r.description)
                if m: 
                    r.date = m.group(1)
                    r.description = r.description[len(m.group(0)):]
            results.append(r)
        return results
        
    def translate(self, string, input="en", output="fr", **kwargs):
        """ Returns the translation of the given string in the desired output language.
        """
        url = URL(GOOGLE + "language/translate", method=GET, query={
                "v" : 1.0,
                "q" : string,
         "langpair" : input+"|"+output
        })
        kwargs.setdefault("cached", False)
        kwargs.setdefault("throttle", self.throttle)
        data = url.download(**kwargs)
        data = json.loads(data)
        data = (data.get("responseData") or {}).get("translatedText", "")
        data = decode_entities(data)
        return u(data)
        
#--- YAHOO -------------------------------------------------------------------------------------------
# https://developer.apps.yahoo.com/wsregapp/

YAHOO = "http://search.yahooapis.com/"
YAHOO_LICENSE = "Bsx0rSzV34HQ9sXprWCaAWCHCINnLFtRF_4wahO1tiVEPpFSltMdqkM1z6Xubg"

class Yahoo(SearchEngine):

    def __init__(self, license=None, throttle=0.1):
        SearchEngine.__init__(self, license or YAHOO_LICENSE, throttle)
        self.format = lambda x: decode_entities(x) # < > & are encoded in XML input.

    def search(self, query, type=SEARCH, start=1, count=10, sort=RELEVANCY, size=None, cached=True, **kwargs):
        """ Returns a list of results from Yahoo for the given query.
            - type : SEARCH, IMAGE or NEWS,
            - start: maximum 1000 results => start 1-100 with count=10, 1000/count,
            - count: maximum 100, or 50 for images.
            There is a daily limit of 5000 queries.
        """
        url = YAHOO
        if   type == SEARCH : url += "WebSearchService/V1/webSearch?"
        elif type == IMAGE  : url += "ImageSearchService/V1/imageSearch?"
        elif type == NEWS   : url += "NewsSearchService/V1/newsSearch?"
        else:
            raise SearchEngineTypeError
        if not query or count < 1 or start > 1000/count: 
            return Results(YAHOO, query, type)
        url = URL(url, method=GET, query={
              "appid" : self.license or "",
              "query" : query,
              "start" : 1 + (start-1) * count,
            "results" : min(count, type==IMAGE and 50 or 100)
        })
        kwargs.setdefault("throttle", self.throttle)
        try: 
            data = url.download(cached=cached, **kwargs)
        except HTTP403Forbidden:
            raise SearchEngineLimitError
        data = xml.dom.minidom.parseString(bytestring(data))
        data = data.childNodes[0]
        results = Results(YAHOO, query, type)
        results.total = data.attributes.get("totalResultsAvailable")
        results.total = results.total and int(results.total.value) or None
        for x in data.getElementsByTagName("Result"):
            r = Result(url=None)
            r.url         = self.format(self._parse(x, "Url"))
            r.title       = self.format(self._parse(x, "Title"))
            r.description = self.format(self._parse(x, "Summary"))
            r.date        = self.format(self._parse(x, "ModificationDate"))
            r.author      = self.format(self._parse(x, "Publisher"))
            r.language    = self.format(self._parse(x, "Language"))
            results.append(r)
        return results
            
    def _parse(self, element, tag):
        # Returns the value of the first child with the given XML tag name (or None).
        tags = element.getElementsByTagName(tag)
        if len(tags) > 0 and len(tags[0].childNodes) > 0:
            assert tags[0].childNodes[0].nodeType == xml.dom.minidom.Element.TEXT_NODE
            return tags[0].childNodes[0].nodeValue

#--- BING --------------------------------------------------------------------------------------------
# http://www.bing.com/developers/s/API%20Basics.pdf
# http://www.bing.com/developers/createapp.aspx

BING = "http://api.search.live.net/json.aspx"
BING_LICENSE = "D6F2EEA455BC0D155BB20EB857066DE85619EC3F"

class Bing(SearchEngine):

    def __init__(self, license=None, throttle=0.1):
        SearchEngine.__init__(self, license or BING_LICENSE, throttle)

    def search(self, query, type=SEARCH, start=1, count=10, sort=RELEVANCY, size=None, cached=True, **kwargs):
        """" Returns a list of results from Bing for the given query.
            - type : SEARCH, IMAGE or NEWS,
            - start: maximum 1000 results => start 1-100 with count=10, 1000/count,
            - count: maximum 50, or 15 for news,
            - size : for images, either SMALL, MEDIUM or LARGE.
            There is no daily query limit.
        """
        url = BING+"?"
        if   type == SEARCH : s = "web"
        elif type == IMAGE  : s = "image"
        elif type == NEWS   : s = "news"
        else:
            raise SearchEngineTypeError
        if not query or count < 1 or start > 1000/count: 
            return Results(BING, query, type)
        url = URL(url, method=GET, query={
                 "Appid" : self.license or "",
               "sources" : s, 
                 "query" : query,
             s+".offset" : 1 + (start-1) * count,
              s+".count" : min(count, type==NEWS and 15 or 50),
                "format" : "json",
         "Image.Filters" : { TINY : "Size:Small", 
                            SMALL : "Size:Small", 
                           MEDIUM : "Size:Medium", 
                            LARGE : "Size:Large" }.get(size,"")
        })
        kwargs.setdefault("throttle", self.throttle)
        data = url.download(cached=cached, **kwargs)
        data = json.loads(data)
        data = data.get("SearchResponse", {}).get(s.capitalize(), {})
        results = Results(BING, query, type)
        results.total = int(data.get("Total", 0))
        for x in data.get("Results", []):
            r = Result(url=None)
            r.url         = self.format(x.get("MediaUrl", x.get("Url")))
            r.title       = self.format(x.get("Title"))
            r.description = self.format(x.get("Description", x.get("Snippet")))
            r.date        = self.format(x.get("DateTime", x.get("Date")))
            results.append(r)
        return results

#--- TWITTER -----------------------------------------------------------------------------------------
# http://apiwiki.twitter.com/

TWITTER = "http://search.twitter.com/"
TWITTER_LICENSE = None

# Words starting with a # and with punctuation at the tail stripped.
TWITTER_HASHTAG = re.compile(r"(\s|^)(#[a-z0-9_\-]+)", re.I)

class Twitter(SearchEngine):
    
    def __init__(self, license=None, throttle=0.4):
        SearchEngine.__init__(self, license or TWITTER_LICENSE, throttle)

    def search(self, query, type=SEARCH, start=1, count=10, sort=RELEVANCY, size=None, cached=False, **kwargs):
        """ Returns a list of results from Twitter for the given query.
            - type : SEARCH or TRENDS,
            - start: maximum 1500 results (10 for trends) => start 1-15 with count=100, 1500/count,
            - count: maximum 100, or 10 for trends.
            There is an hourly limit of 150+ queries (actual amount undisclosed).
        """
        url = TWITTER
        if   type == TRENDS: url += "trends.json"
        elif type == SEARCH: 
            url += "search.json?"
            url += urllib.urlencode((
                ("q", bytestring(query)),
                ("page", start),
                ("rpp", min(count, type==TRENDS and 10 or 100))
            ))
        else:
            raise SearchEngineTypeError
        if not query or count < 1 or start > 1500/count: 
            return Results(TWITTER, query, type)
        kwargs.setdefault("throttle", self.throttle)
        try: 
            data = URL(url).download(cached=cached, **kwargs)
        except HTTP420Error:
            raise SearchEngineLimitError
        data = json.loads(data)
        results = Results(TWITTER, query, type)
        results.total = None
        for x in data.get("results", data.get("trends", [])):
            r = Result(url=None)
            r.url         = self.format(x.get("source", x.get("url")))
            r.description = self.format(x.get("text", x.get("name")))
            r.date        = self.format(x.get("created_at", data.get("as_of")))
            r.author      = self.format(x.get("from_user"))
            r.profile     = self.format(x.get("profile_image_url")) # Profile picture URL.
            r.language    = self.format(x.get("iso_language_code"))
            results.append(r)
        return results

def author(name):
    """ Returns a Twitter query-by-author-name that can be passed to Twitter.search().
        For example: Twitter().search(author("tom_de_smedt"))
    """
    return "from:%s" % name

def hashtags(string):
    """ Returns a list of hashtags (words starting with a #hash) from a tweet.
    """
    return [b for a,b in TWITTER_HASHTAG.findall(string)]

#--- WIKIPEDIA ---------------------------------------------------------------------------------------
# http://en.wikipedia.org/w/api.php

WIKIPEDIA = "http://en.wikipedia.org/w/api.php"
WIKIPEDIA_LICENSE = None

# Pattern for meta links (e.g. Special:RecentChanges).
# http://en.wikipedia.org/wiki/Main_namespace
WIKIPEDIA_NAMESPACE  = ["Main", "User", "Wikipedia", "File", "MediaWiki", "Template", "Help", "Category", "Portal", "Book"]
WIKIPEDIA_NAMESPACE += [s+" talk" for s in WIKIPEDIA_NAMESPACE] + ["Talk", "Special", "Media"]
WIKIPEDIA_NAMESPACE += ["WP", "WT", "MOS", "C", "CAT", "Cat", "P", "T", "H", "MP", "MoS", "Mos"]
_wikipedia_namespace = re.compile(r"^"+"|".join(WIKIPEDIA_NAMESPACE)+":", re.I)

# Pattern to identify disambiguation pages.
WIKIPEDIA_DISAMBIGUATION = "<a href=\"/wiki/Help:Disambiguation\" title=\"Help:Disambiguation\">disambiguation</a> page"

# Pattern to identify references, e.g. [12]
WIKIPEDIA_REFERENCE = r"\s*\[[0-9]{1,3}\]"

class Wikipedia(SearchEngine):
    
    def __init__(self, license=None, throttle=3.0, language="en"):
        SearchEngine.__init__(self, license or WIKIPEDIA_LICENSE, throttle)
        self.language = language

    def search(self, query, type=SEARCH, start=1, count=1, sort=RELEVANCY, size=None, cached=True, **kwargs):
        """ Returns a WikipediaArticle for the given query.
        """
        url = WIKIPEDIA.replace("en.", "%s." % self.language) + "?"
        url = URL(url, method=GET, query={
            "action" : "parse",
              "page" : query.lower().replace(" ","_"),
         "redirects" : 1,
            "format" : "json"
        })
        kwargs.setdefault("timeout", 30) # Parsing the article can take some time.
        kwargs.setdefault("throttle", self.throttle)
        data = url.download(cached=cached, **kwargs)
        data = json.loads(data)
        data = data.get("parse", {})
        a = self._parse_article(data)
        a = self._parse_article_sections(a, data)
        a = self._parse_article_section_structure(a)
        if not a.html or "id=\"noarticletext\"" in a.html:
            return None
        return a
    
    def _parse_article(self, data):
        return WikipediaArticle(
                  title = data.get("displaytitle", ""),
                 source = data.get("text", {}).get("*", ""),
         disambiguation = data.get("text", {}).get("*", "").find(WIKIPEDIA_DISAMBIGUATION) >= 0,
                  links = [x["*"] for x in data.get("links", []) if not _wikipedia_namespace.match(x["*"])],
             categories = [x["*"] for x in data.get("categories", [])],
               external = [x for x in data.get("externallinks", [])],
                  media = [x for x in data.get("images", [])],
              languages = dict([(x["lang"], x["*"]) for x in data.get("langlinks", [])]),
              language  = self.language)
    
    def _parse_article_sections(self, article, data):
        # If "References" is a section in the article,
        # the HTML will contain a marker <h*><span class="mw-headline" id="References">.
        # http://en.wikipedia.org/wiki/Section_editing
        t = article.title
        i = 0
        for x in data.get("sections", {}):
            a = x.get("anchor")
            if a:
                p = r"<h.>\s*.*?\s*<span class=\"mw-headline\" id=\"%s\">" % a
                p = re.compile(p)
                m = p.search(article.source, i)
                if m:
                    j = m.start()
                    article.sections.append(WikipediaSection(article, 
                        title = t,
                        start = i, 
                         stop = j,
                        level = int(x.get("level", 2))-1))
                    t = x.get("line", "")
                    i = j
        return article
    
    def _parse_article_section_structure(self, article):
        # Sections with higher level are children of previous sections with lower level.
        for i, s2 in enumerate(article.sections):
            for s1 in reversed(article.sections[:i]):
                if s1.level < s2.level:
                    s2.parent = s1
                    s1.children.append(s2)
                    break
        return article

class WikipediaArticle:
    
    def __init__(self, title=u"", source=u"", links=[], categories=[], languages={}, disambiguation=False, **kwargs):
        """ An article on Wikipedia returned from Wikipedia.search().
            WikipediaArticle.string contains the HTML content.
        """
        self.title          = title          # Article title.
        self.source         = source         # Article HTML content.
        self.sections       = []             # Article sections.
        self.links          = links          # List of titles of linked articles.
        self.categories     = categories     # List of categories. As links, prepend "Category:".
        self.external       = []             # List of external links.
        self.media          = []             # List of linked media (images, sounds, ...)
        self.languages      = languages      # Dictionary of (language, article)-items, e.g. Cat => ("nl", "Kat")
        self.language       = "en"           # Article language.
        self.disambiguation = disambiguation # True when the article is a disambiguation page.
        for k,v in kwargs.items():
            setattr(self, k, v)
    
    def download(self, media, **kwargs):
        """ Downloads an item from WikipediaArticle.media and returns the content.
            Note: images on Wikipedia can be quite large, and this method uses screen-scraping,
                  so Wikipedia might not like it that you download media in this way.
            To save the media in a file: 
            data = article.download(media)
            open(filename+extension(media),"w").write(data)
        """
        url = "http://%s.wikipedia.org/wiki/File:%s" % (self.__dict__.get("language", "en"), media)
        if url not in cache:
            time.sleep(1)
        data = URL(url).download(**kwargs)
        data = re.search(r"http://upload.wikimedia.org/.*?/%s" % media, data)
        data = data and URL(data.group(0)).download(**kwargs) or None
        return data
    
    def _plaintext(self, string, **kwargs):
        """ Strips HTML tags, whitespace and Wikipedia markup from the HTML source, including:
            metadata, info box, table of contents, annotations, thumbnails, disambiguation link.
            This is called internally from WikipediaArticle.string.
        """
        s = string
        s = strip_between("<table class=\"metadata", "</table>", s) # Metadata.
        s = strip_between("<table id=\"toc", "</table>", s)         # Table of contents.
        s = strip_between("<table class=\"infobox", "</table>", s)  # Infobox.
        s = strip_element(s, "table", "class=\"navbox")             # Navbox.
        s = strip_between("<div id=\"annotation", "</div>", s)      # Annotations.
        s = strip_between("<div class=\"dablink", "</div>", s)      # Disambiguation message.
        s = strip_between("<div class=\"magnify", "</div>", s)      # Thumbnails.
        s = strip_between("<div class=\"thumbcaption", "</div>", s) # Thumbnail captions.
        s = re.sub(r"<img class=\"tex\".*?/>", "[math]", s)         # LaTex math images.
        s = plaintext(s, **kwargs)
        s = re.sub(r"\[edit\]\s*", "", s) # [edit] is language dependent (e.g. nl => "[bewerken]")
        s = s.replace("[", " [").replace("  [", " [") # Space before inline references.
        #s = re.sub(WIKIPEDIA_REFERENCE, " ", s)      # Remove inline references.
        return s
        
    def plaintext(self, **kwargs):
        return self._plaintext(self.source, **kwargs)
    
    @property
    def html(self):
        return self.source
        
    @property
    def string(self):
        return self.plaintext()
        
    def __repr__(self):
        return "WikipediaArticle(title=%s)" % repr(self.title)

class WikipediaSection:
    
    def __init__(self, article, title=u"", start=0, stop=0, level=1):
        """ A (nested) section in the content of a WikipediaArticle.
        """
        self.article  = article # WikipediaArticle the section is part of.
        self.parent   = None    # WikipediaSection the section is part of.
        self.children = []      # WikipediaSections belonging to this section.
        self.title    = title   # Section title.
        self._start   = start   # Section start index in WikipediaArticle.string.
        self._stop    = stop    # Section stop index in WikipediaArticle.string.
        self._level   = level   # Section depth.

    def plaintext(self, **kwargs):
        return self.article._plaintext(self.source, **kwargs)

    @property
    def source(self):
        return self.article.source[self._start:self._stop]
        
    @property
    def html(self):
        return self.source
        
    @property
    def string(self):
        return self.plaintext()
        
    @property
    def content(self):
        # ArticleSection.string, minus the title.
        s = self.plaintext()
        if s == self.title or s.startswith(self.title+"\n"):
            return s[len(self.title):].lstrip()
        return s

    @property
    def level(self):
        return self._level
        
    depth = level

    def __repr__(self):
        return "Section(title='%s')" % bytestring(self.title)

#article = Wikipedia().search("nodebox")
#for section in article.sections:
#    print "  "*(section.level-1) + section.title
#if article.media:
#    data = article.download(article.media[0])
#    f = open(article.media[0], "w")
#    f.write(data)
#    f.close()
#    
#article = Wikipedia(language="nl").search("borrelnootje")
#print article.string

#--- FLICKR ------------------------------------------------------------------------------------------
# http://www.flickr.com/services/api/

FLICKR = "http://api.flickr.com/services/rest/"
FLICKR_LICENSE = "787081027f43b0412ba41142d4540480"

INTERESTING = "interesting"

class Flickr(SearchEngine):
    
    def __init__(self, license=None, throttle=1.0):
        SearchEngine.__init__(self, license or FLICKR_LICENSE, throttle)

    def search(self, query, type=IMAGE, start=1, count=10, sort=RELEVANCY, size=None, cached=True, **kwargs):
        """ Returns a list of results from Flickr for the given query.
            Retrieving the URL of a result (i.e. image) requires an additional query.
            - type : SEARCH,
            - start: maximum undefined,
            - count: maximum 500,
            - sort : RELEVANCY, LATEST or INTERESTING.
            There is no daily limit.
        """
        url = FLICKR+"?"
        url = URL(url, method=GET, query={        
           "api_key" : self.license or "",
            "method" : "flickr.photos.search",
              "text" : query.replace(" ", "_"),
              "page" : start,
          "per_page" : min(count, 500),
              "sort" : { RELEVANCY : "relevance", 
                            LATEST : "date-posted-desc", 
                       INTERESTING : "interestingness-desc" }.get(sort)
        })
        if kwargs.get("copyright", True) is False:
            # http://www.flickr.com/services/api/flickr.photos.licenses.getInfo.html
            # 5: "Attribution-ShareAlike License"
            # 7: "No known copyright restriction"
            url.query["license"] = "5,7"
        kwargs.setdefault("throttle", self.throttle)
        data = url.download(cached=cached, **kwargs)
        data = xml.dom.minidom.parseString(bytestring(data))
        results = Results(FLICKR, query, type)
        results.total = int(data.getElementsByTagName("photos")[0].getAttribute("total"))
        for x in data.getElementsByTagName("photo"):
            r = FlickrResult(url=None)
            r.__dict__["_id"]       = x.getAttribute("id")
            r.__dict__["_size"]     = size
            r.__dict__["_license"]  = self.license
            r.__dict__["_throttle"] = self.throttle
            r.description = self.format(x.getAttribute("title"))
            r.author      = self.format(x.getAttribute("owner"))
            results.append(r)
        return results
        
class FlickrResult(Result):
    
    @property
    def url(self):
        # Retrieving the url of a FlickrResult (i.e. image location) requires another query.
        # Note: the "Original" size no longer appears in the response,
        # so Flickr might not like it if we download it.
        url = FLICKR + "?method=flickr.photos.getSizes&photo_id=%s&api_key=%s" % (self._id, self._license)
        data = URL(url).download(throttle=self._throttle)
        data = xml.dom.minidom.parseString(bytestring(data))
        size = { TINY : "Thumbnail", 
                SMALL : "Small", 
               MEDIUM : "Medium", 
                LARGE : "Original" }.get(self._size, MEDIUM)
        for x in data.getElementsByTagName("size"):
            if size == x.getAttribute("label"):
                return x.getAttribute("source")
            if size == "Original":
                url = x.getAttribute("source")
                url = url[:-len(extension(url))-2] + "_o" + extension(url)
                return u(url)

#images = Flickr().search("kitten", count=10, size=SMALL)
#for img in images:
#    print bytestring(img.description)
#    print img.url
#
#data = img.download()
#f = open("kitten"+extension(img.url), "w")
#f.write(data)
#f.close()

#--- NEWS FEED ---------------------------------------------------------------------------------------
# Based on the Universal Feed Parser by Mark Pilgrim:
# http://www.feedparser.org/

from feed import feedparser

class Newsfeed(SearchEngine):
    
    def __init__(self, license=None, throttle=1.0):
        SearchEngine.__init__(self, license, throttle)
    
    def search(self, query, type=NEWS, start=1, count=10, sort=LATEST, size=SMALL, cached=True, **kwargs):
        """ Returns a list of results from the given RSS or Atom newsfeed URL.
        """ 
        kwargs.setdefault("throttle", self.throttle)
        data = URL(query).download(cached=cached, **kwargs)
        data = feedparser.parse(bytestring(data))
        results = Results(query, query, NEWS)
        results.total = None
        for x in data["entries"]:
            s = "\n\n".join([v.get("value") for v in x.get("content", [])]) or x.get("summary")
            r = Result(url=None)
            r.url         = self.format(x.get("link"))
            r.title       = self.format(x.get("title"))
            r.description = self.format(s)
            r.date        = self.format(x.get("updated"))
            r.author      = self.format(x.get("author"))
            r.language    = self.format(x.get("content") and \
                                x.get("content")[0].get("language") or \
                                               data.get("language"))
            results.append(r) 
        return results           

feeds = {
    "Nature": "http://www.nature.com/nature/current_issue/rss/index.html",
    "Science": "http://www.sciencemag.org/rss/podcast.xml",
    "Herald Tribune": "http://www.iht.com/rss/frontpage.xml",
    "TIME": "http://feeds.feedburner.com/time/topstories",
    "CNN": "http://rss.cnn.com/rss/edition.rss",
    "Processing": "http://www.processingblogs.org/feed/atom/"

}

#for r in Newsfeed().search(feeds["Nature"]):
#    print r.title
#    print r.author
#    print r.url
#    print plaintext(r.description)
#    print

#--- WEB SORT ----------------------------------------------------------------------------------------

SERVICES = {
    GOOGLE : Google,
     YAHOO : Yahoo,
      BING : Bing,   
   TWITTER : Twitter,
 WIKIPEDIA : Wikipedia,
    FLICKR : Flickr
}

def sort(terms=[], context="", service=GOOGLE, license=None, strict=True, reverse=False, **kwargs):
    """ Returns a list of (percentage, term)-tuples for the given list of terms.
        Sorts the terms in the list according to search result count.
        When a context is defined, sorts according to relevancy to the context, e.g.:
        sort(terms=["black", "green", "red"], context="Darth Vader") =>
        yields "black" as the best candidate, because "black Darth Vader" is more common in search results.
        - terms   : list of search terms,
        - context : term used for sorting,
        - service : web service name (GOOGLE, YAHOO, BING, ...)
        - license : web service license id,
        - strict  : when True the query constructed from term + context is wrapped in quotes.
    """
    service = SERVICES.get(service, SearchEngine)(license)
    R = []
    for word in terms:
        q = reverse and context+" "+word or word+" "+context
        q.strip()
        q = strict and "\"%s\"" % q or q
        r = service.search(q, count=1, **kwargs)
        R.append(r)        
    s = float(sum([r.total for r in R])) or 1.0
    R = [(r.total/s, r.query) for r in R]
    R = sorted(R, reverse=True)    
    return R

#print sort(["black", "happy"], "darth vader", GOOGLE)

#### DOCUMENT OBJECT MODEL ###########################################################################
# Tree traversal of HTML source code.
# The Document Object Model (DOM) is a cross-platform and language-independent convention 
# for representing and interacting with objects in HTML, XHTML and XML documents.
# BeautifulSoup is wrapped in Document, Element and Text classes that resemble the Javascript DOM.
# BeautifulSoup can of course be used directly since it is imported here.
# http://www.crummy.com/software/BeautifulSoup/

from soup import BeautifulSoup
SOUP = (
    BeautifulSoup.BeautifulSoup, 
    BeautifulSoup.Tag, 
    BeautifulSoup.NavigableString,
    BeautifulSoup.Comment
)

NODE, TEXT, COMMENT, ELEMENT, DOCUMENT = \
    "node", "text", "comment", "element", "document"

#--- NODE --------------------------------------------------------------------------------------------

class Node:
    
    def __init__(self, html, type=NODE):
        """ The base class for Text, Comment and Element.
            All DOM nodes can be navigated in the same way (e.g. Node.parent, Node.children, ...)
        """
        self.type = type
        self._p = not isinstance(html, SOUP) and BeautifulSoup.BeautifulSoup(u(html)) or html

    @property
    def _beautifulSoup(self):
        # If you must, access the BeautifulSoup object with Node._beautifulSoup.
        return self._p

    def __eq__(self, other):
        # Two Node objects containing the same BeautifulSoup object, are the same.
        return isinstance(other, Node) and hash(self._p) == hash(other._p)
    
    def _wrap(self, x):
        # Navigating to other nodes yields either Text, Element or None.
        if isinstance(x, BeautifulSoup.Comment):
            return Comment(x)
        if isinstance(x, BeautifulSoup.NavigableString):
            return Text(x)
        if isinstance(x, BeautifulSoup.Tag):
            return Element(x)
    
    @property
    def parent(self):
        return self._wrap(self._p.parent)
    @property
    def children(self):
        return hasattr(self._p, "contents") and [self._wrap(x) for x in self._p.contents] or []
    @property
    def next_sibling(self):
        return self._wrap(self._p.nextSibling)
    @property
    def previous_sibling(self):
        return self._wrap(self._p.previousSibling)
    next, previous = next_sibling, previous_sibling

    def traverse(self, visit=lambda node: None):
        """ Executes the visit function on this node and each of its child nodes.
        """
        visit(self); [node.traverse(visit) for node in self.children]
        
    def __len__(self):
        return len(self.children)
    def __iter__(self):
        return iter(self.children)
    def __getitem__(self, index):
        return self.children[index]

    def __repr__(self):
        return "Node(type=%s)" % repr(self.type)
    def __str__(self):
        return bytestring(self.__unicode__())
    def __unicode__(self):
        return u(self._p)
    html = source = __unicode__

#--- TEXT --------------------------------------------------------------------------------------------

class Text(Node):
    """ Text represents a chunk of text without formatting in a HTML document.
        For example: "the <b>cat</b>" is parsed to [Text("the"), Element("cat")].
    """    
    def __init__(self, string):
        Node.__init__(self, string, type=TEXT)
    def __repr__(self):
        return "Text(%s)" % repr(self._p)
    
class Comment(Text):
    """ Comment represents a comment in the HTML source code.
        For example: "<!-- comment -->".
    """
    def __init__(self, string):
        Node.__init__(self, string, type=COMMENT)
    def __repr__(self):
        return "Comment(%s)" % repr(self._p)

#--- ELEMENT -----------------------------------------------------------------------------------------

class Element(Node):
    
    def __init__(self, html):
        """ Element represents an element or tag in the HTML source code.
            For example: "<b>hello</b>" is a "b"-Element containing a child Text("hello").
        """
        Node.__init__(self, html, type=ELEMENT)

    @property
    def tagname(self):
        return self._p.name
    tag = tagName = tagname
    
    @property
    def attributes(self):
        return self._p._getAttrMap()

    @property
    def id(self):
        return self.attributes.get("id")
        
    def get_elements_by_tagname(self, v):
        """ Returns a list of nested Elements with the given tag name.
            The tag name can include a class (e.g. div.header) or an id (e.g. div#content).
        """
        if isinstance(v, basestring) and "#" in v:
            v1, v2 = v.split("#")
            v1 = v1 in ("*","") or v1
            return [Element(x) for x in self._p.findAll(v1, id=v2)]
        if isinstance(v, basestring) and "." in v:
            v1, v2 = v.split(".")
            v1 = v1 in ("*","") or v1
            return [Element(x) for x in self._p.findAll(v1, v2)]
        return [Element(x) for x in self._p.findAll(v in ("*","") or v)]
    by_tag = get_elements_by_tagname

    def get_element_by_id(self, v):
        """ Returns the first nested Element with the given id attribute value.
        """
        return ([Element(x) for x in self._p.findAll(id=v, limit=1) or []]+[None])[0]
    by_id = get_element_by_id
    
    def get_elements_by_classname(self, v):
        """ Returns a list of nested Elements with the given class attribute value.
        """
        return [Element(x) for x in (self._p.findAll(True, v))]
    by_class = get_elements_by_classname

    def get_elements_by_attribute(self, **kwargs):
        """ Returns a list of nested Elements with the given attribute value.
        """
        return [Element(x) for x in (self._p.findAll(True, attrs=kwargs))]
    by_attribute = get_elements_by_attribute
    
    @property
    def content(self):
        """ Yields the element content as a unicode string.
        """
        return u"".join([u(x) for x in self._p.contents])
    
    @property
    def source(self):
        """ Yields the HTML source as a unicode string (tag + content).
        """
        return u(self._p)
    html = source

    def __repr__(self):
        return "Element(tag='%s')" % bytestring(self.tagname)

#--- DOCUMENT ----------------------------------------------------------------------------------------

class Document(Element):
    
    def __init__(self, html):
        """ Document is the top-level element in the Document Object Model.
            It contains nested Element, Text and Comment nodes.
        """
        Node.__init__(self, html.strip(), type=DOCUMENT)

    @property
    def head(self):
        return self._wrap(self._p.head)
    @property
    def body(self):
        return self._wrap(self._p.body)
    @property
    def tagname(self):
        return None
    tag = tagname
    
    def __repr__(self):
        return "Document()"

#article = Wikipedia().search("Document Object Model")
#dom = Document(article.html)
#print dom.get_element_by_id("References").source
#print [element.attributes["href"] for element in dom.get_elements_by_tagname("a")]
#print dom.get_elements_by_tagname("p")[0].next.previous.children[0].parent.__class__
#print

#### WEB CRAWLER #####################################################################################

class Link:
    
    def __init__(self, url, description="", relation=""):
        """ A hyperlink parsed from a HTML document, in the form:
            <a href="url"", title="description", rel="relation">xxx</a>.
        """
        self.url, self.description, self.relation = u(url), u(description), u(relation)
    
    def __repr__(self):
        return "Link(url=%s)" % repr(self.url)

    # Used for sorting in Spider.links:
    def __eq__(self, link):
        return self.url == link.url
    def __ne__(self, link):
        return self.url != link.url
    def __lt__(self, link):
        return self.url < link.url
    def __gt__(self, link):
        return self.url > link.url

class HTMLLinkParser(SGMLParser):
    
    def __init__(self):
        SGMLParser.__init__(self)

    def parse(self, html):
        """ Returns a list of Links parsed from the given HTML string.
        """
        if html is None:
            return None
        self._data = []
        self.feed(self.clean(html))
        self.close()
        self.reset()
        return self._data
    
    def unknown_starttag(self, tag, attributes):
        if tag == "a":
            attributes = dict(attributes)
            if "href" in attributes:
                link = Link(url = attributes.get("href"),
                    description = attributes.get("title"),
                       relation = attributes.get("rel", ""))
                self._data.append(link)

def base(url):
    """ Returns the URL domain name: 
        http://en.wikipedia.org/wiki/Web_crawler => en.wikipedia.org
    """
    return urlparse.urlparse(url).netloc
    
def abs(url, base=None):
    """ Returns the absolute URL:
        ../media + http://en.wikipedia.org/wiki/ => http://en.wikipedia.org/media
    """
    return urlparse.urljoin(base, url)

DEPTH   = "depth"
BREADTH = "breadth"

class Spider:
    
    def __init__(self, links=[], delay=20, queue=False, parser=HTMLLinkParser().parse):
        """ A spider can be used to browse the web in an automated manner.
            It visits the list of starting URLs, parses links from their content, visits those, etc.
            - Links can be prioritized by overriding Spider.rank().
            - Links can be ignored by overriding Spider.follow().
            - Each visited link is passed to Spider.visit(), which can be overridden.
        """
        self.parse   = parser
        self.delay   = delay # Delay between visits to the same (sub)domain.
        self.queue   = queue # Wait for delay or parse other links in the meantime?
        self.__queue = {}    # Domain name => time last visited.
        self.visited = {}    # URLs already visited => backlink count.
        self._links  = []    # URLs scheduled for a visit: (priority, time, Link, referrer).
        for link in links:
            if not isinstance(link, Link):
                link = Link(url=link)
            self._links.append((-1.0, 0.0, link, None)) # -1.0 = highest priority.
            self.visited[link.url] = 0
    
    @property
    def links(self):
        return [link for priority, t, link, referrer in self._links]
    
    def _elapsed(self, url):
        # Elapsed time since last visit to this (sub)domain.
        return time.time() - self.__queue.get(base(url), 0)
        
    def _queue(self, url):
        # Log the url + time visited.
        self.__queue[base(url)] = time.time()
    
    def normalize(self, url):
        """ Called from Spider.crawl() to normalize URLs.
            This can involve stripping the query-string, for example.
        """
        return url
    
    @property
    def done(self):
        return len(self._links) == 0
    
    def crawl(self, method=DEPTH, **kwargs):
        """ Visits the next link in the Spider.links list.
            If the link is on a domain recently visited (< Spider.delay), skips it.
            Parses the content at the link for new links and adds them to the list,
            according to their Spider.rank().
            Visited links (and content) are passed to Spider.visit().
        """
        b = False
        for i, (priority, t, link, referrer) in enumerate(self._links):
            # Find the highest priority link to visit,
            # on a (sub)domain which we haven't visited in 10 seconds (politeness).
            if self._elapsed(link.url) > self.delay:
                b = True
            if b or self.queue is True:
                break
        if b is True:
            priority, t, link, referrer = self._links.pop(i)
            url  = URL(link.url)
            mime = url.mimetype
            html = None
            #link.url = url.redirect or link.url
            if mime == "text/html":
                # Parse new links from HTML web pages.
                # They are scheduled for a visit according to their Spider.rank() score.
                try:
                    html = url.download(**kwargs)
                    for new in self.parse(html):
                        new.url = abs(new.url, base=url.redirect or link.url)
                        new.url = self.normalize(new.url)
                        # Only visit new links for which Spider.follow() is True.
                        # If the link was visited already, increase its backlink count
                        # (but don't reschedule it).
                        if self.visited.get(new.url) is not None and base(new.url) != base(link.url):
                            self.visited[new.url] += 1
                        if self.visited.get(new.url) is None and self.follow(new, referrer=link):
                            self.visited[new.url] = 0
                            bisect.insort(self._links, # Keep priority sort order.
                                (1-self.rank(new, referrer=link, method=method), time.time(), new, link))
                except URLError: # Raised in URL.download().
                    mime = None
            if mime is None:
                self.fail(link, referrer)
            else:
                self.visit(link, referrer, source=html)
            self.visited[link.url] = 1
            self._queue(link.url)
        time.sleep(0.01)
        
    def visit(self, link, referrer=None, source=None):
        """ Called from Spider.crawl() when the link is crawled.
            When html=None, this means that the link is not a web page (and was not parsed),
            or possibly that a URLTimeout occured (content size too big).
        """
        #print "visited", link.url, "from", referrer.url
        pass
        
    def fail(self, link, referrer=None):
        """ Called from Spider.crawl() for link whose MIME-type could not be determined,
            or which raised a URLError on download.
        """
        #print "failed:", link.url
        pass
    
    def follow(self, link, referrer=None):
        """ Called from Spider.crawl() to determine if it should follow this link.
        """
        return True
        
    def rank(self, link, referrer=None, **kwargs):
        """ Called from Spider.crawl() to determine the priority of this link,
            as a number between 0.0-1.0. Links with higher priority are visited first.
        """
        # URLs with a query string scores lower, 
        # could just be a different sort order for example.
        # It is essential we don't spend too much time exploring these.
        if "?" in link.url: 
            return 0.7
        # Breadth-first search prefers external links to other (sub)domains.
        method = kwargs.get("method", DEPTH)
        external = base(link.url) != base(referrer.url)
        if not external:
            if method == BREADTH: 
                return 0.8
            if method == DEPTH:
                return 1.0
        return 0.9
        
    def backlinks(self, url):
        """ Returns the number of inbound links to the given URL (so far).
        """
        return self.visited.get(url, 0)

#class Spiderling(Spider):
#    def visit(self, link, referrer=None, source=None):
#        print "visited:", repr(link.url), "from:", referrer
#    def fail(self, link, referrer=None):
#        print "failed:", link.url
#
#s = Spiderling(links=["http://www.python.org/"], delay=3, queue=True)
#while not s.done:
#    s.crawl(method=BREADTH, cached=True)

#### LANGUAGE #########################################################################################
# Language code => (language, region)

language = {
       u'af': [u'Afrikaans', u'South Africa'],
       u'ar': [u'Arabic', u'Middle East'],
    u'ar-ae': [u'Arabic', u'United Arab Emirates'],
    u'ar-bh': [u'Arabic', u'Bahrain'],
    u'ar-dz': [u'Arabic', u'Algeria'],
    u'ar-eg': [u'Arabic', u'Egypt'],
    u'ar-iq': [u'Arabic', u'Iraq'],
    u'ar-jo': [u'Arabic', u'Jordan'],
    u'ar-kw': [u'Arabic', u'Kuwait'],
    u'ar-lb': [u'Arabic', u'Lebanon'],
    u'ar-ly': [u'Arabic', u'Libya'],
    u'ar-ma': [u'Arabic', u'Morocco'],
    u'ar-om': [u'Arabic', u'Oman'],
    u'ar-qa': [u'Arabic', u'Qatar'],
    u'ar-sa': [u'Arabic', u'Saudi Arabia'],
    u'ar-sy': [u'Arabic', u'Syria'],
    u'ar-tn': [u'Arabic', u'Tunisia'],
    u'ar-ye': [u'Arabic', u'Yemen'],
       u'be': [u'Belarusian', u'Belarus'],
       u'bg': [u'Bulgarian', u'Bulgaria'],
       u'ca': [u'Catalan', u'Andorra'],
       u'cs': [u'Czech', u'Czech Republic'],
       u'da': [u'Danish', u'Denmark'],
       u'de': [u'German', u'Germany'],
    u'de-at': [u'German', u'Austria'],
    u'de-ch': [u'German', u'Switzerland'],
    u'de-li': [u'German', u'Liechtenstein'],
    u'de-lu': [u'German', u'Luxembourg'],
       u'el': [u'Greek', u'Greece'],
       u'en': [u'English', u'Caribbean'],
    u'en-au': [u'English', u'Australia'],
    u'en-bz': [u'English', u'Belize'],
    u'en-ca': [u'English', u'Canada'],
    u'en-gb': [u'English', u'United Kingdom'],
    u'en-ie': [u'English', u'Ireland'],
    u'en-jm': [u'English', u'Jamaica'],
    u'en-nz': [u'English', u'New Zealand'],
    u'en-tt': [u'English', u'Trinidad'],
    u'en-us': [u'English', u'United States'],
    u'en-za': [u'English', u'South Africa'],
       u'es': [u'Spanish', u'Spain'],
    u'es-ar': [u'Spanish', u'Argentina'],
    u'es-bo': [u'Spanish', u'Bolivia'],
    u'es-cl': [u'Spanish', u'Chile'],
    u'es-co': [u'Spanish', u'Colombia'],
    u'es-cr': [u'Spanish', u'Costa Rica'],
    u'es-do': [u'Spanish', u'Dominican Republic'],
    u'es-ec': [u'Spanish', u'Ecuador'],
    u'es-gt': [u'Spanish', u'Guatemala'],
    u'es-hn': [u'Spanish', u'Honduras'],
    u'es-mx': [u'Spanish', u'Mexico'],
    u'es-ni': [u'Spanish', u'Nicaragua'],
    u'es-pa': [u'Spanish', u'Panama'],
    u'es-pe': [u'Spanish', u'Peru'],
    u'es-pr': [u'Spanish', u'Puerto Rico'],
    u'es-py': [u'Spanish', u'Paraguay'],
    u'es-sv': [u'Spanish', u'El Salvador'],
    u'es-uy': [u'Spanish', u'Uruguay'],
    u'es-ve': [u'Spanish', u'Venezuela'],
       u'et': [u'Estonian', u'Estonia'],
       u'eu': [u'Basque', u'Basque Country'],
       u'fa': [u'Farsi', u'Iran'],
       u'fi': [u'Finnish', u'Finland'],
       u'fo': [u'Faeroese', u'Faroe Islands'],
       u'fr': [u'French', u'France'],
    u'fr-be': [u'French', u'Belgium'],
    u'fr-ca': [u'French', u'Canada'],
    u'fr-ch': [u'French', u'Switzerland'],
    u'fr-lu': [u'French', u'Luxembourg'],
       u'ga': [u'Irish' , u'Ireland'],
       u'gd': [u'Gaelic', u'Scotland'],
       u'he': [u'Hebrew', 'Israel'],
       u'hi': [u'Hindi', u'India'],
       u'hr': [u'Croatian', u'Croatia'],
       u'hu': [u'Hungarian', u'Hungary'],
       u'id': [u'Indonesian', u'Indonesia'],
       u'is': [u'Icelandic', u'Iceland'],
       u'it': [u'Italian', u'Italy'],
    u'it-ch': [u'Italian', u'Switzerland'],
       u'ja': [u'Japanese', u'Japan'],
       u'ji': [u'Yiddish', u''],
       u'ko': [u'Korean', u'Johab'],
       u'lt': [u'Lithuanian', u'Lithuania'],
       u'lv': [u'Latvian', u'Latvia'],
       u'mk': [u'Macedonian', u'Macedonia'],
       u'ms': [u'Malaysian', u'Malaysia'],
       u'mt': [u'Maltese', u'Malta'],
       u'nl': [u'Dutch', u'Netherlands'],
    u'nl-be': [u'Dutch', u'Belgium'],
       u'no': [u'Norwegian', u'Nynorsk'],
       u'pl': [u'Polish', u'Poland'],
       u'pt': [u'Portuguese', u'Portugal'],
    u'pt-br': [u'Portuguese', u'Brazil'],
       u'rm': [u'Rhaeto-Romanic', u'Italy'],
       u'ro': [u'Romanian', u'Romania'],
    u'ro-mo': [u'Romanian', u'Republic of Moldova'],
       u'ru': [u'Russian', u'Russia'],
    u'ru-mo': [u'Russian', u'Republic of Moldova'],
       u'sb': [u'Sorbian', u'Lusatia'],
       u'sk': [u'Slovak', u'Slovakia'],
       u'sl': [u'Slovenian', u'Slovenia'],
       u'sq': [u'Albanian', u'Albania'],
       u'sr': [u'Serbian', u'Serbia'],
       u'sv': [u'Swedish', u'Sweden'],
    u'sv-fi': [u'Swedish', u'Finland'],
       u'sx': [u'Sotho', u'South Africa'],
       u'sz': [u'Sami', u'Sapmi'],
       u'th': [u'Thai', u'Thailand'],
       u'tn': [u'Tswana', u'Botswana'],
       u'tr': [u'Turkish', u'Turkey'],
       u'ts': [u'Tsonga', u'South Africa'],
       u'uk': [u'Ukrainian', u'Ukraine'],
       u'ur': [u'Urdu', u'Pakistan'],
       u've': [u'Venda', u'South Africa'],
       u'vi': [u'Vietnamese', u'Vietnam'],
       u'xh': [u'Xhosa', u'South Africa'],
       u'zh': [u'Chinese', u'China'],
    u'zh-cn': [u'Chinese', u'China'],
    u'zh-hk': [u'Chinese', u'Hong Kong'],
    u'zh-sg': [u'Chinese', u'Singapore'],
    u'zh-tw': [u'Chinese', u'Taiwan'],
       u'zu': [u'Zulu', u'South Africa']
}

#######################################################################################################

def test():
    # A shallow test to see if all the services can be reached.
    p = cache.path
    cache.path = TMP
    cache.clear()
    for engine in (Google, Yahoo, Bing, Twitter, Wikipedia, Flickr):
        try: 
            engine().search("tiger")
            print engine.__name__, "ok."
        except:
            print engine.__name__, "error."
    cache.path = p
    
#test()
