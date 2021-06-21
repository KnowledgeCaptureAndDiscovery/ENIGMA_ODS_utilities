import hashlib, json, requests, re
from termcolor import colored

endpoints = [
    {
        "wiki": {
            "url": "",
            "username": "",
            "password": ""
        },
        "sparql": {
            "url": "",
            "username": "",
            "password": ""
        }
    },
]

hashRegex = r'Checksum \(E\)=[a-zA-Z0-9]{40}'
emptySet = r'\{\{\#set:\|?\}\}'
doubleOr = r'\|\s*\|'
exServ = "organicdatacuration.org"
inServ = "localhost:8080"

class SessionWithUrlBase(requests.Session):
    def __init__(self, url_base=None, *args, **kwargs):
        super(SessionWithUrlBase, self).__init__(*args, **kwargs)
        self.url_base = url_base

    def request(self, method, url, **kwargs):
        modified_url = self.url_base + url
        return super(SessionWithUrlBase, self).request(method, modified_url, **kwargs)


def check_all_files (generalConf):
    #Create sessions:
    sparqlSession = createSparqlSession(generalConf["sparql"])
    botSession = createWikiBotSession(generalConf["wiki"])
    wikiurl = generalConf["wiki"]["url"]

    tkn = getCSRFToken(botSession)
    updatePage = getUpdatePageF(botSession, tkn)

    wikiEntries = getAllFiles(sparqlSession, wikiurl)
    print("Auth onto " + wikiurl)

    # -- Output stuff
    namelen = 0
    for entry in wikiEntries:
        newNameLen = len(entry["page"].split("/")[-1])
        if (namelen < newNameLen):
            namelen = newNameLen
    def printline (st, pname, fhash):
        cst = "      "
        if (st == 0):
            cst = colored(" OK   ", "yellow")
        elif (st == 1):
            cst = colored(" NEW  ", "green")
        elif (st == 2):
            cst = colored(" UPD  ", "green")
        pname = pname + " "*(namelen - len(pname))
        print(cst, "|", pname, "|", fhash)

    def printerror (pname, fname):
        cst = colored(" ERROR", "red")
        pname = pname + " "*(namelen - len(pname))
        print(cst, "|", pname, "|", fname)

    print("STATUS | NAME" + " "*(namelen-3) + "| Hash" )
    # -- End output stuff

    for entry in wikiEntries:
        pagename = entry["page"].split("/")[-1]
        fileurl = entry["file"]
        filehash = entry["hash"]
        if (pagename.endswith(".csv")):
            # Do no process pages that end with .csv
            continue
        if not "images" in fileurl:
            printerror(pagename, fileurl)
            continue
        nHash = getExternalFileHash(fileurl)
        if (nHash != None and nHash != filehash):
            #Create new page content
            content = getWikiContent(botSession, pagename)
            newContent = re.sub(hashRegex, '', content)
            newContent = re.sub(emptySet, '', newContent)
            newContent = re.sub(doubleOr, '|', newContent)
            newContent += "\n{{#set:|Checksum (E)="+nHash+"}}"
            newContent = re.sub(r'\n+', '\n', newContent)
            #Update page
            updatePage(pagename, newContent)
            if (filehash == None):
                printline(1, pagename, nHash)
            else:
                printline(2, pagename, nHash)
                print(filehash, nHash)
        elif nHash == None:
            printerror(pagename, fileurl)
        else:
            printline(0, pagename, filehash)
    print("")

def createSparqlSession (conf):
    #sparqlSession = requests.Session()
    sparqlSession = SessionWithUrlBase(url_base=conf["url"])
    sparqlSession.auth = (conf["username"] , conf["password"])
    return sparqlSession

def createWikiBotSession (conf):
    #botSession = requests.Session()
    botSession = SessionWithUrlBase(url_base=conf["url"] + "/api.php")
    # First we need to retrieve login token
    PARAMS_TOKEN = {
        'action':"query",
        'meta':"tokens",
        'type':"login",
        'format':"json"
    }
    loginTokenRes = botSession.get("", params=PARAMS_TOKEN).json()
    LOGIN_TOKEN = loginTokenRes['query']['tokens']['logintoken']

    # Go to http://organicdatacuration.org/enigma_new/index.php/Special:BotPasswords for lgname & lgpassword, and add them below
    PARAMS_LOGIN = {
        'action': "login",
        'lgname': conf["username"],
        'lgpassword': conf["password"],
        'lgtoken': LOGIN_TOKEN,
        'format': "json"
    }

    botSession.post("", data=PARAMS_LOGIN).json()
    return botSession

def getAllFiles (sparql, wikiurl):
    query = "PREFIX wiki: <" + wikiurl.replace(exServ, inServ) + "/index.php/Special:URIResolver/> "\
          + "SELECT ?page ?file ?hash WHERE {"\
          + "  ?page wiki:Property-3AHasContentUrl_-28E-29 ?file ."\
          + "  optional {?page wiki:Property-3AChecksum_-28E-29 ?hash}"\
          + "} ORDER BY ?page"

    response = sparql.post("", data = {'query': query})
    res = json.loads(response.text)

    query_results=[]
    revised_pages = set()
    for item in res['results']['bindings']:
        entry = {} 
        pg = item["page"]["value"] if ("page" in item) else None
        if not pg in revised_pages:
            revised_pages.add(pg)
            entry["page"] = pg
            entry["file"] = item["file"]["value"] if ("file" in item) else None
            entry["hash"] = item["hash"]["value"] if ("hash" in item) else None
            query_results.append(entry)
    
    return query_results

def getExternalFileHash (fileurl):
    #Get the file
    sha = hashlib.sha1()
    try:
        with requests.get(fileurl, stream=True) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=8192): 
                sha.update(chunk)

        digest = sha.hexdigest()
        return digest
    except:
        print("Error downloading " + fileurl)
        return None

def getCSRFToken (session):
    PARAMS_CSRFT = {
        "action": "query",
        "meta": "tokens",
        "format": "json"
    }

    response = session.get("", params=PARAMS_CSRFT)
    DATA = response.json()
    return DATA['query']['tokens']['csrftoken']

def getWikiContent (session, page):
    PARAMS = {
        "action": "query",
        "format": "json",
        "prop": "revisions",
        "titles": page,
        "rvprop": "content"
    }
    response = session.get("", params=PARAMS)
    DATA = response.json()
    pages = DATA["query"]["pages"]
    for page in pages:
        return pages[page]["revisions"][0]["*"]

def getUpdatePageF (session, token):
    def _getEditParams(page, append):
        return {
            "action": "edit",
            "title": page,
            "section": "0",
            "format": "json",
            "text": append,
            "token": token
        }
    def _updatePage(page, content):
        req = session.post("", data=_getEditParams(page, content))
        data = req.json()
    return _updatePage

for endpoint in endpoints:
    check_all_files(endpoint)
