import hashlib, json, requests, re

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

    tkn = getCSRFToken(botSession)
    updatePage = getUpdatePageF(botSession, tkn)

    wikiEntries = getAllFiles(sparqlSession, generalConf["wiki"]["url"])
    i = 0
    for entry in wikiEntries:
        #print("page: " + entry["page"] + "\tfile: " + entry["file"] + "\thash: " + (entry["hash"] if (entry["hash"]) else ""))
        if not "images" in entry["file"]:
            print("Warning! this page: " + entry["page"] + " has an invalid reference!")
            continue
        nHash = getExternalFileHash(entry["file"])
        if (nHash != entry["hash"]):
            pagename = entry["page"].split("/")[-1]
            print(pagename + " has a new hash: " + nHash)
            content = getWikiContent(botSession, pagename)
            newContent = re.sub(hashRegex, '', content)
            newContent = re.sub(emptySet, '', newContent)
            newContent = re.sub(doubleOr, '|', newContent)
            newContent += "\n{{#set:|Checksum (E)="+nHash+"}}"
            newContent = re.sub(r'\n+', '\n', newContent)
            #print(content + "\n will be replaces with\n" + newContent)
            updatePage(pagename, newContent)
        else:
            print(entry["page"] + " old hash is still valid")

def createSparqlSession (conf):
    sparqlSession = SessionWithUrlBase(url_base=conf["url"])
    sparqlSession.auth = (conf["username"] , conf["password"])
    return sparqlSession

def createWikiBotSession (conf):
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

    loginReq = botSession.post("", data=PARAMS_LOGIN).json()
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
        print(page + " updated!")
    return _updatePage

check_all_files(endpoints[0])
